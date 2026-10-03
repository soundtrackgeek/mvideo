import AVKit
import XCTest
@testable import MVideo

final class RemoteNavigationTests: XCTestCase {
    @MainActor func testSwipesMoveBothWaysAndRespectPlaylistBounds() async throws {
        try await withPlayback { model, session, coordinator in
            for gesture in coordinator.playlistGestures {
                XCTAssertEqual(gesture.allowedTouchTypes, [NSNumber(value: UITouch.TouchType.indirect.rawValue)])
                XCTAssertTrue(gesture.allowedPressTypes.isEmpty, "Touch swipes must not be implemented as arrow-button presses.")
            }
            let right = completedSwipe(.right)
            XCTAssertTrue(coordinator.gestureRecognizer(right, shouldReceive: RemoteTouch()))
            coordinator.changeVideo(right)
            XCTAssertEqual(model.queue.index, 1)
            coordinator.changeVideo(right)
            XCTAssertEqual(model.queue.index, 1, "One gesture advances only once.")
            try await waitForPlayback(model)
            let sought = await model.player.seek(to: CMTime(seconds: 4, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
            XCTAssertTrue(sought)
            model.player.play()
            XCTAssertGreaterThan(model.player.currentTime().seconds, 3)
            let left = completedSwipe(.left)
            XCTAssertTrue(coordinator.gestureRecognizer(left, shouldReceive: RemoteTouch()))
            coordinator.changeVideo(left)
            XCTAssertEqual(model.queue.current, "boost", "Previous means the preceding video, even after three seconds.")
            try await waitForPlayback(model)
            let firstItem = model.player.currentItem
            XCTAssertTrue(coordinator.gestureRecognizer(left, shouldReceive: RemoteTouch()))
            coordinator.changeVideo(left)
            XCTAssertEqual(model.queue.index, 0)
            XCTAssertTrue(model.player.currentItem === firstItem)
            XCTAssertFalse(model.preparing, "Previous at the start leaves playback alone.")

            model.select("last")
            try await waitForPlayback(model)
            XCTAssertTrue(coordinator.gestureRecognizer(right, shouldReceive: RemoteTouch()))
            coordinator.changeVideo(right)
            XCTAssertTrue(model.finished)
            XCTAssertNil(model.queue.current)
            XCTAssertFalse(coordinator.gestureRecognizer(right, shouldReceive: RemoteTouch()))
        }
    }

    @MainActor func testTouchStartKeepsSwipeValidWhenAVKitRevealsControls() async throws {
        try await withPlayback { model, session, coordinator in
            let controller = AVPlayerViewController()
            let animation = ImmediateAnimationCoordinator()
            let swipe = completedSwipe(.right)
            XCTAssertTrue(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()))
            coordinator.playerViewController(controller, willTransitionToVisibilityOfTransportBar: true, with: animation)
            coordinator.changeVideo(swipe)
            XCTAssertEqual(model.queue.index, 1, "Revealing controls during the swipe must not cancel it.")
            try await waitForPlayback(model)
            XCTAssertFalse(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()), "A new swipe with controls already open stays native.")
            coordinator.playerViewController(controller, willTransitionToVisibilityOfTransportBar: false, with: animation)
            model.player.pause()
            XCTAssertFalse(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()), "Paused playback retains scrubbing.")
            model.player.play()
            model.error = "Playback unavailable"
            XCTAssertFalse(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()))
            model.error = nil
            model.preparing = true
            XCTAssertFalse(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()))
        }
    }

    @MainActor func testStaleSwipesCannotSkipNewItemsOrChangeFloatingPlayback() async throws {
        try await withPlayback { model, session, coordinator in
            let swipe = completedSwipe(.right)
            XCTAssertTrue(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()))
            model.next()
            try await waitForPlayback(model)
            coordinator.changeVideo(swipe)
            XCTAssertEqual(model.queue.index, 1, "A swipe begun on the old video cannot skip its successor.")
            XCTAssertTrue(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()))
            session.minimize()
            XCTAssertFalse(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()))
            coordinator.changeVideo(swipe)
            XCTAssertEqual(model.queue.index, 1)
            session.restore()
            coordinator.playerViewControllerWillStartPictureInPicture(AVPlayerViewController())
            XCTAssertFalse(coordinator.gestureRecognizer(swipe, shouldReceive: RemoteTouch()))
            session.didStartPictureInPicture()
            coordinator.changeVideo(swipe)
            XCTAssertEqual(model.queue.index, 1)
            session.stop()
            coordinator.changeVideo(swipe)
            XCTAssertEqual(model.queue.index, 1)
        }
    }

    @MainActor private func withPlayback(_ body: (PlayerModel, PlaybackSession, NativePlayer.Coordinator) async throws -> Void) async throws {
        let file = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "Normalization", withExtension: "mp4"))
        let server = try FixtureServer(media: Data(contentsOf: file))
        let origin = try await server.start()
        defer { server.stop() }
        let model = PlayerModel(api: API(Connection(origin: origin, token: "test")), ids: ["boost", "cut", "last"], title: "Swipe test")
        let session = PlaybackSession()
        session.play(model)
        defer { session.stop() }
        try await waitForPlayback(model)
        try await body(model, session, NativePlayer.Coordinator(model: model, session: session))
    }

    @MainActor private func waitForPlayback(_ model: PlayerModel) async throws {
        for _ in 0..<100 {
            if !model.preparing || model.error != nil { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertNil(model.error)
        XCTAssertFalse(model.preparing)
        XCTAssertEqual(model.player.currentItem?.status, .readyToPlay)
        XCTAssertGreaterThan(model.player.rate, 0)
    }

    @MainActor private func completedSwipe(_ direction: UISwipeGestureRecognizer.Direction) -> PlaylistSwipeGestureRecognizer {
        let swipe = CompletedSwipe()
        swipe.direction = direction
        return swipe
    }
}

// Exercise eligibility and routing separately from actual touch recognition.
// XCUIRemote can synthesize button presses, but has no touchpad-swipe API.
private final class RemoteTouch: UITouch {
    override var type: UITouch.TouchType { .indirect }
}
private final class CompletedSwipe: PlaylistSwipeGestureRecognizer {
    override var state: UIGestureRecognizer.State {
        get { .ended }
        set { }
    }
}
private final class ImmediateAnimationCoordinator: NSObject, AVPlayerViewControllerAnimationCoordinator {
    func addCoordinatedAnimations(_ animations: (() -> Void)?, completion: ((Bool) -> Void)? = nil) {
        animations?()
        completion?(true)
    }
}
