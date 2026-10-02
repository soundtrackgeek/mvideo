import AVFoundation
import Network
import XCTest
@testable import MVideo

final class NormalizationTests: XCTestCase {
    func testMetadataCompatibilityAndGainValidation() throws {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let old = try decoder.decode(PlaybackResponse.self, from: Data(#"{"state":"ready","mode":"direct","url":"/media/a"}"#.utf8))
        XCTAssertNil(old.normalization)
        let boost = PlaybackNormalization(state: "ready", profile: "track-gain-v1", gainDb: 6)
        XCTAssertEqual(try XCTUnwrap(boost.gain), 1.9952623, accuracy: 0.00001)
        for value in [Double.nan, .infinity, 12.01, -101] {
            XCTAssertNil(PlaybackNormalization(state: "ready", profile: "track-gain-v1", gainDb: value).gain)
        }
        XCTAssertNil(PlaybackNormalization(state: "ready", profile: "future-profile", gainDb: 0).gain)
        XCTAssertNil(PlaybackNormalization(state: "unavailable", profile: "track-gain-v1", gainDb: nil).gain)
    }

    func testPCMInterleavingBoostAttenuationGuardAndSmoothToggle() throws {
        func render(_ processor: NormalizationProcessor, _ samples: [Float], channels: Int = 2) -> [Float] {
            var samples = samples
            let frames = samples.count / channels
            samples.withUnsafeMutableBytes { bytes in
                var list = AudioBufferList(mNumberBuffers: 1, mBuffers: AudioBuffer(
                    mNumberChannels: UInt32(channels), mDataByteSize: UInt32(bytes.count), mData: bytes.baseAddress))
                processor.process(&list, frames: frames)
            }
            return samples
        }
        var format = AudioStreamBasicDescription(mSampleRate: 48000, mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked,
            mBytesPerPacket: 8, mFramesPerPacket: 1, mBytesPerFrame: 8, mChannelsPerFrame: 2, mBitsPerChannel: 32, mReserved: 0)
        let boost = NormalizationProcessor(gain: 2, enabled: true)
        boost.prepare(format)
        XCTAssertEqual(render(boost, [0.2, -0.2, 0.8, -0.8, .nan, .infinity]), [0.4, -0.4, 1, -1, 0, 0])
        let cut = NormalizationProcessor(gain: 0.5, enabled: true)
        cut.prepare(format)
        XCTAssertEqual(render(cut, [0.2, -0.4]), [0.1, -0.2])
        cut.enabled.store(false, ordering: .relaxed)
        let ramp = render(cut, Array(repeating: 0.2, count: 1920))
        XCTAssertLessThan(ramp[0], 0.101)
        XCTAssertEqual(ramp[0], ramp[1], "Both channels must get identical gain at each frame.")
        XCTAssertEqual(try XCTUnwrap(ramp.last), 0.2, accuracy: 0.00001)
        XCTAssertEqual(render(cut, [1.2, -1.2]), [1.2, -1.2], "Off preserves the original samples.")
        format.mChannelsPerFrame = 6
        cut.prepare(format)
        XCTAssertFalse(cut.supported.load(ordering: .relaxed))
        XCTAssertEqual(render(cut, [0.2, -0.2]), [0.2, -0.2])
    }

    @MainActor func testHTTPPlaybackGainSeekNextFallbackAndPreference() async throws {
        let file = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "Normalization", withExtension: "mp4"))
        let server = try FixtureServer(media: Data(contentsOf: file))
        let origin = try await server.start()
        defer { server.stop() }
        let preferences = try XCTUnwrap(UserDefaults(suiteName: "normalization-tests-" + UUID().uuidString))
        let api = API(Connection(origin: origin, token: "test"))
        let model = PlayerModel(api: api, ids: ["boost", "cut", "unmeasured"], title: "Test", preferences: preferences)
        defer { model.stop() }
        XCTAssertTrue(model.normalizationEnabled)
        model.start()
        try await waitForAudio(model)
        var processor = try XCTUnwrap(model.normalization?.processor)
        XCTAssertEqual(ratio(processor), pow(10, 6 / 20.0), accuracy: 0.01)
        XCTAssertNotNil(model.player.currentItem?.audioMix)
        let sought = await model.player.seek(to: CMTime(seconds: 4, preferredTimescale: 600))
        XCTAssertTrue(sought)
        let frames = processor.processedFrames.load(ordering: .relaxed)
        model.player.play()
        try await Task.sleep(for: .seconds(1))
        XCTAssertGreaterThan(processor.processedFrames.load(ordering: .relaxed), frames)
        XCTAssertEqual(ratio(processor), pow(10, 6 / 20.0), accuracy: 0.01)
        model.toggleNormalization()
        try await Task.sleep(for: .seconds(1))
        XCTAssertEqual(ratio(processor), 1, accuracy: 0.01)
        XCTAssertFalse(preferences.bool(forKey: "normalizeVolume"))
        model.toggleNormalization()
        // Drive the real end notification, rather than manually advancing the queue.
        let soughtEnd = await model.player.seek(to: CMTime(seconds: 11.7, preferredTimescale: 600))
        XCTAssertTrue(soughtEnd)
        model.player.play()
        for _ in 0..<100 {
            if model.queue.index == 1 && model.normalization?.processor.processedFrames.load(ordering: .relaxed) ?? 0 > 0 { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertEqual(model.queue.index, 1)
        try await waitForAudio(model)
        processor = try XCTUnwrap(model.normalization?.processor)
        XCTAssertEqual(ratio(processor), pow(10, -8 / 20.0), accuracy: 0.01)
        model.next()
        for _ in 0..<100 {
            if !model.preparing { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertNil(model.error)
        XCTAssertEqual(model.current?.id, "unmeasured")
        XCTAssertNil(model.normalization)
        XCTAssertNil(model.player.currentItem?.audioMix)
        XCTAssertEqual(model.player.volume, 1)
        XCTAssertTrue(model.normalizationMessage.contains("no usable measurement"))
        model.toggleNormalization()
        let reopened = PlayerModel(api: api, ids: [], title: "Test", preferences: preferences)
        XCTAssertFalse(reopened.normalizationEnabled)
        model.stop()
        XCTAssertNil(model.normalization)
    }

    @MainActor private func waitForAudio(_ model: PlayerModel) async throws {
        for _ in 0..<150 {
            if let processor = model.normalization?.processor,
               processor.processedFrames.load(ordering: .relaxed) > 0,
               Float(bitPattern: processor.inputPeak.load(ordering: .relaxed)) > 0.0001 { break }
            if model.error != nil { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertNil(model.error)
        XCTAssertFalse(model.preparing)
        let processor = try XCTUnwrap(model.normalization?.processor)
        XCTAssertTrue(processor.supported.load(ordering: .relaxed))
        XCTAssertGreaterThan(processor.processedFrames.load(ordering: .relaxed), 0, "The real HTTP MP4 must invoke the native audio tap.")
    }

    private func ratio(_ processor: NormalizationProcessor) -> Float {
        Float(bitPattern: processor.outputPeak.load(ordering: .relaxed))
            / Float(bitPattern: processor.inputPeak.load(ordering: .relaxed))
    }
}

/// Disposable loopback fixture, including byte ranges for AVPlayer seeks. It serves
/// generated media only and never accesses the user's library or paired session.
final class FixtureServer {
    private let listener: NWListener
    private let queue = DispatchQueue(label: "normalization-http-test")
    private let media: Data
    private let artists: [String: String]
    private var connections: [NWConnection] = []
    init(media: Data, artists: [String: String] = [:]) throws {
        self.media = media
        self.artists = artists
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        listener = try NWListener(using: parameters)
    }
    func start() async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            var resumed = false
            listener.stateUpdateHandler = { [weak self] state in
                guard let self, !resumed else { return }
                switch state {
                case .ready:
                    resumed = true
                    continuation.resume(returning: URL(string: "http://127.0.0.1:\(self.listener.port!.rawValue)")!)
                case .failed(let error):
                    resumed = true
                    continuation.resume(throwing: error)
                default: break
                }
            }
            listener.newConnectionHandler = { [weak self] connection in
                guard let self else { return }
                self.connections.append(connection)
                connection.start(queue: self.queue)
                self.receive(connection, accumulated: Data())
            }
            listener.start(queue: queue)
        }
    }
    func stop() {
        listener.cancel()
        queue.async { self.connections.forEach { $0.cancel() }; self.connections = [] }
    }
    private func receive(_ connection: NWConnection, accumulated: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, complete, error in
            guard let self else { return }
            let input = accumulated + (data ?? Data())
            if let range = input.range(of: Data("\r\n\r\n".utf8)) {
                self.respond(connection, request: String(decoding: input[..<range.upperBound], as: UTF8.self))
            } else if !complete && error == nil && input.count < 65536 {
                self.receive(connection, accumulated: input)
            } else { connection.cancel() }
        }
    }
    private func respond(_ connection: NWConnection, request: String) {
        let lines = request.components(separatedBy: "\r\n")
        let parts = (lines.first ?? "").split(separator: " ")
        guard parts.count >= 2 else { connection.cancel(); return }
        let path = String(parts[1])
        let id = String(path.split(separator: "/").last ?? "")
        var body: Data
        var headers = ""
        var status = "200 OK"
        if path.hasPrefix("/api/") {
            let object: [String: Any]
            if path.hasPrefix("/api/videos/") {
                object = ["id": id, "artist": artists[id] ?? "Test", "title": id, "year": 2000, "warnings": []]
            } else {
                let normalization: [String: Any] = id == "unmeasured"
                    ? ["state": "unavailable", "profile": "track-gain-v1", "reason": "error"]
                    : ["state": "ready", "profile": "track-gain-v1", "gain_db": id == "boost" ? 6 : -8]
                object = ["state": "ready", "mode": "direct", "url": "/media/\(id).mp4", "normalization": normalization]
            }
            body = try! JSONSerialization.data(withJSONObject: object)
            headers += "Content-Type: application/json\r\n"
        } else {
            body = media
            headers += "Content-Type: video/mp4\r\nAccept-Ranges: bytes\r\n"
            if let range = lines.first(where: { $0.lowercased().hasPrefix("range: bytes=") }) {
                let bounds = range.split(separator: "=")[1].split(separator: "-", omittingEmptySubsequences: false)
                let start = Int(bounds[0]) ?? 0
                let end = min(media.count - 1, bounds.count > 1 ? Int(bounds[1]) ?? media.count - 1 : media.count - 1)
                guard start <= end, start >= 0 else { connection.cancel(); return }
                body = media.subdata(in: start..<(end + 1))
                status = "206 Partial Content"
                headers += "Content-Range: bytes \(start)-\(end)/\(media.count)\r\n"
            }
        }
        let head = "HTTP/1.1 \(status)\r\n\(headers)Content-Length: \(body.count)\r\nConnection: close\r\n\r\n"
        connection.send(content: Data(head.utf8) + (parts[0] == "HEAD" ? Data() : body), completion: .contentProcessed { _ in connection.cancel() })
    }
}
