# Playback volume normalization — 0.9.0

The owner completed analysis on 2026-10-02: 15,541 current measurements and 17 errors across 15,558 available videos. Failed analyses retry when `windows-measure-loudness.ps1` is rerun; already measured, unchanged videos are skipped.

## Behavior

Apple TV applies one gain per video through an `MTAudioProcessingTap` attached to its `AVPlayerItem.audioMix` before playback. This handles attenuation and amplification without rewriting the file or decoding audio on the server during playback. The transport bar's **Normalize volume** control defaults on and persists in local preferences. Switching it interpolates the gain briefly to avoid an abrupt discontinuity. Each new item owns a separate processor, preventing the previous video's gain from leaking into the next video.

The server's playback response supplies profile `track-gain-v1` and:

```text
gain_dB = min(-18 - integrated_LUFS, -2 - true_peak_dBTP, 12)
linear_gain = 10 ** (gain_dB / 20)
```

These are mvideo's playback defaults, not a claim of a broadcast delivery standard. The -2 dBTP source-peak margin and +12 dB boost cap take precedence over the loudness target. Peak-limited or very quiet tracks can remain quieter. No automatic compression changes the dynamics within a song.

Only successful, finite measurements matching the current file size/mtime, analysis version and first audio stream index are used. The service also checks the file's current stat data before supplying gain. Failed, missing, below-gate, no-audio, stale and invalid records return an unavailable status, and playback continues at original volume. Old servers also remain playable; the new app indicates that the server needs an update. Older clients ignore the additional response field.

Direct MP4 playback is limited to a single audio track. Files with multiple tracks use the existing first-track remux path, preventing automatic language/default-track selection from applying the wrong gain. Existing compatibility conversions retain first-track stereo/48 kHz output. The native processor supports packed native-endian float32/float64 and signed 16/32-bit mono/stereo PCM, including interleaved and planar buffers; unsupported formats pass through unchanged.

Source true peaks are not a fresh measurement of an AAC playback derivative or the final TV/receiver output. Resampling, AAC encoding and device mixing can change peaks. The processor includes a final sample clamp for unexpected overshoots, but this is **not an oversampled true-peak limiter**. Physical-device listening and output-chain verification remain necessary; the software does not guarantee identical perceived volume for every recording.

## Install

Update the source checkout on the PC, then run the following in administrator PowerShell:

```powershell
git pull --ff-only
.\scripts\windows-update-service.ps1
```

This builds a wheel before stopping the running task, installs only the server package into the configured service Python, restarts a previously running task even if installation reports an error, and verifies the running version through loopback `/health`. A task already stopped is left stopped. The database, loudness data, provider configuration and source media are retained. The package replaces an editable installation if one was used; subsequent updates should use this updater again. The service's older source checkout is not overwritten.

Apple TV **0.9.0 (6)** is available through the existing TestFlight group. The production Windows service was updated to **0.9.1** on 2026-10-02 and retained all measurements. Reopen playback to receive the new response and activate normalization. No repeat analysis is required for the 15,541 valid measurements. For A/B listening, use Normalize volume in the player controls; the 17 error records continue at original volume until successfully remeasured.

## Verification

The server suite covers actual example gains, peak/boost bounds, authenticated metadata, stale/unindexed source changes, failed/missing measurements, unchanged source bytes and an FFmpeg-generated multi-track MP4 whose default track differs from the measured first track.

Native tests serve a generated MP4 over loopback HTTP with byte ranges and run the real `PlayerModel`, `AVPlayer` and audio tap in tvOS Simulator. They inspect input/output sample peaks to verify positive and negative gain, toggle to unity, seek, automatic end-to-next, reset for an unmeasured item and persisted preferences. Separate tests cover sample clipping/nonfinite values, synchronized channel ramps, metadata validation and older responses. The fixture is a generated 12-second 440 Hz sine with a black 64×36 video; it contains no library content.

Delivery and final test results are recorded in [verification](implementation/VERIFICATION.md).

## API references

- [Apple: AVPlayer volume](https://developer.apple.com/documentation/avfoundation/avplayer/volume) describes the player's ordinary 0–1 volume control.
- [Apple: audio processing taps](https://developer.apple.com/documentation/avfoundation/avmutableaudiomixinputparameters/audiotapprocessor) provides access to decoded track data before playback.
- [Apple: pre/post effect taps](https://developer.apple.com/library/archive/qa/qa1783/_index.html) describes the audio-mix processing order.
