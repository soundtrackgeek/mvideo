import AVKit
import XCTest
@testable import MVideo

final class PlaybackSessionTests: XCTestCase {
    @MainActor func testMissingArtistDoesNotNavigateOrMinimize() throws {
        let session = PlaybackSession()
        let model = try makeModel()
        session.play(model)
        defer { session.stop() }

        for artist in [nil, "", " \n\t "] as [String?] {
            model.current = video(artist: artist)
            XCTAssertNil(model.currentArtist)
            session.showArtist()
            XCTAssertNil(session.artistToOpen)
            XCTAssertTrue(session.isFullScreen)
        }
    }

    @MainActor func testArtistActionPreservesPlayerItemAndQueue() throws {
        let session = PlaybackSession()
        let model = try makeModel()
        session.play(model)
        defer { session.stop() }
        model.current = video(artist: "  Björk\n")
        model.queue = QueueCursor(ids: ["first", "second"])
        let queue = model.queue
        let item = AVPlayerItem(asset: AVMutableComposition())
        model.player.replaceCurrentItem(with: item)

        session.showArtist()

        XCTAssertEqual(session.artistToOpen, "Björk")
        XCTAssertEqual(session.presentation, .miniPlayer)
        XCTAssertTrue(session.model === model)
        XCTAssertTrue(model.player.currentItem === item)
        XCTAssertEqual(model.queue, queue)
        session.restore()
        XCTAssertTrue(session.isFullScreen)
        XCTAssertTrue(model.player.currentItem === item)
    }

    @MainActor func testNativePictureInPictureRestorationKeepsPlaybackButCloseStopsIt() async throws {
        let session = PlaybackSession()
        let model = try makeModel()
        session.play(model)
        defer { session.stop() }
        let item = AVPlayerItem(asset: AVMutableComposition())
        model.player.replaceCurrentItem(with: item)
        let controller = AVPlayerViewController()
        let coordinator = NativePlayer.Coordinator(model: model, session: session)
        coordinator.controller = controller
        XCTAssertFalse(coordinator.playerViewControllerShouldAutomaticallyDismissAtPictureInPictureStart(controller))

        coordinator.playerViewControllerWillStartPictureInPicture(controller)
        XCTAssertFalse(coordinator.playerViewControllerShouldDismiss(controller))
        XCTAssertTrue(session.model === model, "AVKit dismissal during PiP startup must not stop the video.")
        XCTAssertTrue(model.player.currentItem === item)
        coordinator.playerViewControllerDidStartPictureInPicture(controller)
        XCTAssertEqual(session.presentation, .systemPictureInPicture)
        let restored = await restore(coordinator, controller: controller)
        XCTAssertTrue(restored)
        coordinator.playerViewControllerDidStopPictureInPicture(controller)
        XCTAssertTrue(session.isFullScreen)
        XCTAssertTrue(session.model === model)
        XCTAssertTrue(model.player.currentItem === item)

        coordinator.playerViewControllerDidStartPictureInPicture(controller)
        coordinator.playerViewControllerDidStopPictureInPicture(controller)
        XCTAssertNil(session.model)
        XCTAssertNil(model.player.currentItem)
    }

    @MainActor func testPictureInPictureFailureLeavesPlaybackAvailable() throws {
        let session = PlaybackSession()
        let model = try makeModel()
        session.play(model)
        defer { session.stop() }
        let item = AVPlayerItem(asset: AVMutableComposition())
        model.player.replaceCurrentItem(with: item)
        let coordinator = NativePlayer.Coordinator(model: model, session: session)
        let controller = AVPlayerViewController()

        coordinator.playerViewControllerWillStartPictureInPicture(controller)
        XCTAssertFalse(coordinator.playerViewControllerShouldDismiss(controller))
        XCTAssertTrue(session.model === model)
        XCTAssertTrue(model.player.currentItem === item)
        coordinator.playerViewController(controller, failedToStartPictureInPictureWithError: NSError(domain: "test", code: 1))

        XCTAssertNotNil(session.pictureInPictureError)
        XCTAssertTrue(session.isFullScreen)
        XCTAssertTrue(model.player.currentItem === item)
        session.minimize()
        XCTAssertEqual(session.presentation, .miniPlayer)
        XCTAssertFalse(coordinator.playerViewControllerShouldDismiss(controller))
        XCTAssertTrue(model.player.currentItem === item)
        session.restore()
        XCTAssertFalse(coordinator.playerViewControllerShouldDismiss(controller))
        XCTAssertNil(session.model, "A failed PiP attempt must clear the startup guard so Menu can end full-screen playback.")
        XCTAssertNil(model.player.currentItem)
    }

    @MainActor func testStaleControllerCallbacksCannotChangeReplacementPlayback() async throws {
        let session = PlaybackSession()
        let original = try makeModel()
        session.play(original)
        original.player.replaceCurrentItem(with: AVPlayerItem(asset: AVMutableComposition()))
        let controller = AVPlayerViewController()
        let stale = NativePlayer.Coordinator(model: original, session: session)
        let replacement = try makeModel()
        session.play(replacement)
        defer { session.stop() }
        let item = AVPlayerItem(asset: AVMutableComposition())
        replacement.player.replaceCurrentItem(with: item)

        XCTAssertFalse(stale.playerViewControllerShouldDismiss(controller))
        XCTAssertTrue(session.model === replacement, "A dismissed outgoing controller must not stop its replacement.")
        XCTAssertTrue(replacement.player.currentItem === item)
        stale.playerViewControllerDidStartPictureInPicture(controller)
        XCTAssertTrue(session.isFullScreen)
        session.didStartPictureInPicture()
        stale.playerViewControllerDidStopPictureInPicture(controller)
        XCTAssertEqual(session.presentation, .systemPictureInPicture)
        stale.playerViewController(controller, failedToStartPictureInPictureWithError: NSError(domain: "test", code: 1))
        XCTAssertNil(session.pictureInPictureError)
        let restored = await restore(stale, controller: controller)
        XCTAssertFalse(restored)
        XCTAssertEqual(session.presentation, .systemPictureInPicture)
        XCTAssertTrue(session.model === replacement)
        XCTAssertTrue(replacement.player.currentItem === item)
        XCTAssertNil(original.player.currentItem)
    }

    @MainActor func testStopClearsPendingNavigationAndPlayback() throws {
        let session = PlaybackSession()
        let model = try makeModel()
        session.play(model)
        model.current = video(artist: "Prince")
        model.player.replaceCurrentItem(with: AVPlayerItem(asset: AVMutableComposition()))
        session.showArtist()
        XCTAssertNotNil(session.artistToOpen)

        session.stop()

        XCTAssertNil(session.model)
        XCTAssertNil(session.artistToOpen)
        XCTAssertNil(model.player.currentItem)
        XCTAssertEqual(model.player.rate, 0)
        XCTAssertFalse(session.isFullScreen)
        session.minimize()
        session.restore()
        session.showArtist()
        XCTAssertNil(session.model)
        XCTAssertNil(session.artistToOpen)
    }

    @MainActor func testHTTPAudioSurvivesArtistNavigationMinimizeRestoreAndAutomaticNext() async throws {
        let file = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "Normalization", withExtension: "mp4"))
        let server = try FixtureServer(media: Data(contentsOf: file), artists: ["boost": "Björk", "cut": "Prince", "last": "a-ha"])
        let origin = try await server.start()
        defer { server.stop() }
        let preferenceDomain = "playback-session-" + UUID().uuidString
        let preferences = try XCTUnwrap(UserDefaults(suiteName: preferenceDomain))
        defer { preferences.removePersistentDomain(forName: preferenceDomain) }
        let api = API(Connection(origin: origin, token: "test"))
        let model = PlayerModel(api: api, ids: ["boost", "cut", "last"], title: "Navigation test", preferences: preferences)
        let session = PlaybackSession()
        session.play(model)
        defer { session.stop() }
        try await waitForAudio(model)
        let item = try XCTUnwrap(model.player.currentItem)
        let processor = try XCTUnwrap(model.normalization?.processor)
        let queue = model.queue
        let sought = await model.player.seek(to: CMTime(seconds: 3, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        XCTAssertTrue(sought)
        model.player.play()
        let position = model.player.currentTime().seconds
        let frames = processor.processedFrames.load(ordering: .relaxed)

        session.showArtist()
        XCTAssertEqual(session.artistToOpen, "Björk")
        XCTAssertEqual(session.presentation, .miniPlayer)
        XCTAssertTrue(model.player.currentItem === item)
        XCTAssertEqual(model.queue, queue)
        XCTAssertEqual(model.player.currentTime().seconds, position, accuracy: 0.2)
        try await waitForProgress(model, since: position)
        XCTAssertGreaterThan(processor.processedFrames.load(ordering: .relaxed), frames, "Artist navigation must leave the native audio tap running.")

        session.restore()
        XCTAssertTrue(session.isFullScreen)
        XCTAssertTrue(model.player.currentItem === item)
        let restoredFrames = processor.processedFrames.load(ordering: .relaxed)
        try await waitForProgress(model, since: model.player.currentTime().seconds)
        XCTAssertGreaterThan(processor.processedFrames.load(ordering: .relaxed), restoredFrames)

        session.minimize()
        XCTAssertTrue(model.player.currentItem === item)
        let minimizedFrames = processor.processedFrames.load(ordering: .relaxed)
        try await waitForProgress(model, since: model.player.currentTime().seconds)
        XCTAssertGreaterThan(processor.processedFrames.load(ordering: .relaxed), minimizedFrames)
        let duration = try await item.asset.load(.duration).seconds
        let soughtEnd = await model.player.seek(to: CMTime(seconds: duration - 0.3, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        XCTAssertTrue(soughtEnd)
        model.player.play()
        for _ in 0..<100 {
            if model.queue.index == 1 { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertEqual(model.queue.index, 1)
        try await waitForAudio(model)
        XCTAssertEqual(model.current?.id, "cut")
        XCTAssertEqual(session.presentation, .miniPlayer)
        XCTAssertFalse(model.player.currentItem === item)
        session.artistToOpen = nil
        session.showArtist()
        XCTAssertEqual(session.artistToOpen, "Prince", "Navigation must follow the playing video after automatic next.")
        session.restore()
        XCTAssertTrue(session.isFullScreen)
        XCTAssertEqual(model.queue.index, 1)

        session.minimize()
        let secondItem = try XCTUnwrap(model.player.currentItem)
        model.next()
        XCTAssertTrue(model.player.currentItem === secondItem, "Preparing the next video must retain an item so system PiP can stay open.")
        try await waitForAudio(model)
        XCTAssertEqual(model.current?.id, "last")
        XCTAssertEqual(model.queue.index, 2)
        XCTAssertEqual(session.presentation, .miniPlayer)
        XCTAssertFalse(model.player.currentItem === secondItem)
        session.artistToOpen = nil
        session.showArtist()
        XCTAssertEqual(session.artistToOpen, "a-ha")
    }

    @MainActor private func makeModel() throws -> PlayerModel {
        let api = API(Connection(origin: try Connection.origin("https://example.com"), token: "test"))
        // An empty queue keeps state tests independent of network requests.
        return PlayerModel(api: api, ids: [], title: "Session test")
    }

    private func video(artist: String?) -> Video {
        Video(id: "first", artist: artist, title: "Song", year: nil, thumbnail: nil, warnings: [], probeError: nil)
    }

    @MainActor private func restore(_ coordinator: NativePlayer.Coordinator, controller: AVPlayerViewController) async -> Bool {
        await withCheckedContinuation { continuation in
            coordinator.playerViewController(controller, restoreUserInterfaceForPictureInPictureStopWithCompletionHandler: { restored in
                continuation.resume(returning: restored)
            })
        }
    }

    @MainActor private func waitForAudio(_ model: PlayerModel) async throws {
        for _ in 0..<150 {
            if model.normalization?.processor.processedFrames.load(ordering: .relaxed) ?? 0 > 0 { break }
            if model.error != nil { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertNil(model.error)
        XCTAssertFalse(model.preparing)
        let processor = try XCTUnwrap(model.normalization?.processor)
        XCTAssertGreaterThan(processor.processedFrames.load(ordering: .relaxed), 0, "The HTTP fixture must produce audio through AVPlayer.")
    }

    @MainActor private func waitForProgress(_ model: PlayerModel, since position: Double, file: StaticString = #filePath, line: UInt = #line) async throws {
        for _ in 0..<50 {
            if model.player.currentTime().seconds > position + 0.25 || model.error != nil { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertNil(model.error, file: file, line: line)
        XCTAssertGreaterThan(model.player.currentTime().seconds, position + 0.25, "Playback must continue after changing presentation.", file: file, line: line)
    }
}
