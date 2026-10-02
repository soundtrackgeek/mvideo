import AVFoundation
import MediaToolbox
import Synchronization

/// One processor per player item. Only the audio callbacks access the mutable DSP
/// state; the UI communicates through atomics, without locks on the render thread.
final class NormalizationProcessor {
    let gain: Float
    let enabled: Atomic<Bool>
    let processedFrames = Atomic<Int64>(0)
    let supported = Atomic<Bool>(false)
    // Diagnostics are sampled once per buffer, including by integration tests.
    let inputPeak = Atomic<UInt32>(0)
    let outputPeak = Atomic<UInt32>(0)
    private var currentGain: Float
    private var rampFrames: Float = 960
    private var format: AudioStreamBasicDescription = .init()

    init(gain: Float, enabled: Bool) {
        self.gain = gain
        self.enabled = Atomic(enabled)
        currentGain = enabled ? gain : 1
    }

    func prepare(_ format: AudioStreamBasicDescription) {
        self.format = format
        currentGain = enabled.load(ordering: .relaxed) ? gain : 1
        rampFrames = Float(max(1, format.mSampleRate * 0.02))
        let flags = format.mFormatFlags
        let isFloat = flags & kAudioFormatFlagIsFloat != 0
        let bits = format.mBitsPerChannel
        let supportedPCM = format.mFormatID == kAudioFormatLinearPCM
            && flags & kAudioFormatFlagIsBigEndian == 0
            && flags & kAudioFormatFlagIsPacked != 0
            && (1...2).contains(format.mChannelsPerFrame)
            && ((isFloat && (bits == 32 || bits == 64))
                || (!isFloat && flags & kAudioFormatFlagIsSignedInteger != 0 && (bits == 16 || bits == 32)))
        supported.store(supportedPCM, ordering: .relaxed)
    }

    func process(_ buffers: UnsafeMutablePointer<AudioBufferList>, frames: Int) {
        guard supported.load(ordering: .relaxed), frames > 0 else { return }
        let isEnabled = enabled.load(ordering: .relaxed)
        let destination: Float = isEnabled ? gain : 1
        let start = currentGain
        let delta = destination - start
        let isFloat = format.mFormatFlags & kAudioFormatFlagIsFloat != 0
        let bytesPerSample = Int(format.mBitsPerChannel / 8)
        var before: Float = 0
        var after: Float = 0
        // AudioBufferList's lightweight view does not allocate. Process planar and
        // interleaved PCM with the same gain at the same frame in every channel.
        for buffer in UnsafeMutableAudioBufferListPointer(buffers) {
            guard let data = buffer.mData else { continue }
            let channels = Int(buffer.mNumberChannels)
            guard channels > 0 else { continue }
            let count = min(frames, Int(buffer.mDataByteSize) / bytesPerSample / channels)
            for frame in 0..<count {
                let level = start + delta * min(1, Float(frame + 1) / rampFrames)
                for channel in 0..<channels {
                    let index = frame * channels + channel
                    let sample: Double
                    if isFloat {
                        sample = bytesPerSample == 4 ? Double(data.assumingMemoryBound(to: Float.self)[index])
                            : data.assumingMemoryBound(to: Double.self)[index]
                    } else {
                        sample = bytesPerSample == 2 ? Double(data.assumingMemoryBound(to: Int16.self)[index]) / 32768
                            : Double(data.assumingMemoryBound(to: Int32.self)[index]) / 2147483648
                    }
                    // Gain is peak-limited before playback. This final sample guard
                    // catches unexpected decoder overshoots; it is not a compressor
                    // or an oversampled true-peak limiter.
                    let output = !isEnabled && start == 1 ? sample
                        : (sample.isFinite ? max(-1, min(1, sample * Double(level))) : 0)
                    before = max(before, Float(abs(sample.isFinite ? sample : 0)))
                    after = max(after, Float(abs(output)))
                    if isFloat {
                        if bytesPerSample == 4 { data.assumingMemoryBound(to: Float.self)[index] = Float(output) }
                        else { data.assumingMemoryBound(to: Double.self)[index] = output }
                    } else if bytesPerSample == 2 {
                        data.assumingMemoryBound(to: Int16.self)[index] = Int16(max(-32768, min(32767, output * 32768)))
                    } else {
                        data.assumingMemoryBound(to: Int32.self)[index] = Int32(max(-2147483648, min(2147483647, output * 2147483648)))
                    }
                }
            }
        }
        currentGain = start + delta * min(1, Float(frames) / rampFrames)
        inputPeak.store(before.bitPattern, ordering: .relaxed)
        outputPeak.store(after.bitPattern, ordering: .relaxed)
        processedFrames.wrappingAdd(Int64(frames), ordering: .relaxed)
    }
}

struct AudioNormalization {
    let mix: AVAudioMix
    let processor: NormalizationProcessor

    static func make(for asset: AVAsset, gain: Float, enabled: Bool) async throws -> AudioNormalization {
        guard gain.isFinite, gain > 0, gain <= pow(10, 12 / 20.0) else {
            throw ServiceError.message("Invalid volume adjustment.")
        }
        let tracks = try await asset.loadTracks(withMediaType: .audio)
        // The server maps the measured first audio track into a single-track
        // rendition. Never apply one track's measurement to multiple tracks.
        guard tracks.count == 1, let track = tracks.first else {
            throw ServiceError.message("Volume normalization is unavailable for this audio track.")
        }
        let processor = NormalizationProcessor(gain: gain, enabled: enabled)
        var callbacks = MTAudioProcessingTapCallbacks(version: kMTAudioProcessingTapCallbacksVersion_0,
            clientInfo: Unmanaged.passUnretained(processor).toOpaque(), init: nil, finalize: nil,
            prepare: nil, unprepare: nil, process: { tap, frames, _, buffers, framesOut, flagsOut in
                let status = MTAudioProcessingTapGetSourceAudio(tap, frames, buffers, flagsOut, nil, framesOut)
                guard status == noErr else { framesOut.pointee = 0; return }
                let value = Unmanaged<NormalizationProcessor>.fromOpaque(MTAudioProcessingTapGetStorage(tap)).takeUnretainedValue()
                value.process(buffers, frames: framesOut.pointee)
            })
        callbacks.`init` = { _, info, storage in
            guard let info else { return }
            // Init/finalize are always balanced, including a failed creation.
            let value = Unmanaged<NormalizationProcessor>.fromOpaque(info).takeUnretainedValue()
            storage.pointee = Unmanaged.passRetained(value).toOpaque()
        }
        callbacks.finalize = { tap in
            Unmanaged<NormalizationProcessor>.fromOpaque(MTAudioProcessingTapGetStorage(tap)).release()
        }
        callbacks.prepare = { tap, _, format in
            let value = Unmanaged<NormalizationProcessor>.fromOpaque(MTAudioProcessingTapGetStorage(tap)).takeUnretainedValue()
            value.prepare(format.pointee)
        }
        var tap: MTAudioProcessingTap?
        let status = MTAudioProcessingTapCreate(kCFAllocatorDefault, &callbacks,
                                               kMTAudioProcessingTapCreationFlag_PreEffects, &tap)
        guard status == noErr, let tap else { throw ServiceError.message("Unable to prepare volume normalization.") }
        let parameters = AVMutableAudioMixInputParameters(track: track)
        parameters.audioTapProcessor = tap
        let mix = AVMutableAudioMix()
        mix.inputParameters = [parameters]
        return AudioNormalization(mix: mix, processor: processor)
    }
}
