import AVFoundation
import XCTest
@testable import MVideo

final class PlaybackIntegrationTests: XCTestCase {
    @MainActor func testRealLibraryHomeQueueAndPlayback() async throws {
        guard let connection = KeychainStore().load() else {
            throw XCTSkip("Pair the simulator with the real library before running playback integration.")
        }
        let api = API(connection)
        // Home starts its catalog and featured-artwork requests independently.
        async let featured: FeaturedResponse = measuredLiveRequest("Home featured") {
            try await api.request("/api/featured")
        }
        let page = try await measuredLiveRequest("Home first page") {
            try await api.videos(scope: Scope())
        }
        let first = try XCTUnwrap(page.items.first, "The real Home page must contain videos.")
        XCTAssertGreaterThanOrEqual(page.total, page.items.count)
        let queue = try await measuredLiveRequest("Full-library queue") {
            try await api.queue(scope: Scope(), shuffle: false, start: first.id)
        }
        XCTAssertGreaterThanOrEqual(queue.ids.count, page.items.count)
        XCTAssertEqual(queue.ids.first, first.id)
        XCTAssertEqual(Set(queue.ids).count, queue.ids.count, "The full-library queue must not repeat videos.")
        if queue.revision == page.revision {
            XCTAssertEqual(queue.ids.count, page.total, "Home playback must queue the whole selection.")
        }
        guard let lucky = page.items.first(where: {
            $0.artist == "'Til Tuesday" && $0.title == "(Believed You Were) Lucky"
        }) else {
            throw XCTSkip("The reported playback sample is no longer on the real Home first page.")
        }
        let prepared: PlaybackResponse = try await measuredLiveRequest("Lucky playback preparation") {
            try await api.request("/api/playback/" + lucky.id, method: "POST")
        }
        XCTAssertEqual(prepared.state, "ready", "The known live sample must be ready to play.")
        XCTAssertNotNil(prepared.url)
        _ = try await featured
    }

    @MainActor private func measuredLiveRequest<T>(_ label: String, operation: () async throws -> T) async rethrows -> T {
        let start = ContinuousClock.now
        print("MVIDEO_LIVE_TIMING \(label) started")
        defer {
            // Log only a fixed stage name and duration, never session or media URLs.
            print("MVIDEO_LIVE_TIMING \(label) elapsed \(start.duration(to: .now))")
        }
        return try await operation()
    }

    @MainActor func testRealLibrarySeekAndAutomaticNext() async throws {
        guard let connection = KeychainStore().load() else {
            throw XCTSkip("Pair the simulator with the real library before running playback integration.")
        }
        let api = API(connection)
        let page = try await api.videos(scope: Scope(artist: "'Til Tuesday"))
        try XCTSkipUnless(page.items.count >= 2, "Real-library sample artist is unavailable.")
        let ids = Array(page.items.prefix(2).map(\.id))
        let preferenceDomain = "live-playback-" + UUID().uuidString
        let preferences = try XCTUnwrap(UserDefaults(suiteName: preferenceDomain))
        defer { preferences.removePersistentDomain(forName: preferenceDomain) }
        let model = PlayerModel(api: api, ids: ids, title: "Integration verification", preferences: preferences)
        defer { model.stop() }
        model.start()
        for _ in 0..<120 {
            if !model.preparing { break }
            try await Task.sleep(for: .milliseconds(250))
        }
        XCTAssertNil(model.error)
        XCTAssertFalse(model.preparing)
        let item = try XCTUnwrap(model.player.currentItem)
        XCTAssertEqual(item.status, .readyToPlay)
        let titleMetadata = try XCTUnwrap(item.externalMetadata.first(where: { $0.identifier == .commonIdentifierTitle }))
        let playbackTitle = try await titleMetadata.load(.stringValue)
        XCTAssertEqual(playbackTitle, model.current?.playbackTitle)
        let audio = try await item.asset.loadTracks(withMediaType: .audio)
        XCTAssertFalse(audio.isEmpty)
        let duration = try await item.asset.load(.duration).seconds
        XCTAssertGreaterThan(duration, 10)
        let sought = await model.player.seek(to: CMTime(seconds: duration / 2, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        XCTAssertTrue(sought)
        XCTAssertEqual(model.player.currentTime().seconds, duration / 2, accuracy: 1)
        model.player.play()
        let start = model.player.currentTime().seconds
        try await Task.sleep(for: .seconds(2))
        XCTAssertGreaterThan(model.player.currentTime().seconds, start + 0.5)
        let prepared: PlaybackResponse = try await api.request("/api/playback/" + ids[0], method: "POST")
        let expectedGain = try XCTUnwrap(prepared.normalization?.gain, "The live sample requires a valid stored measurement.")
        let processor = try XCTUnwrap(model.normalization?.processor)
        XCTAssertEqual(processor.gain, expectedGain, accuracy: 0.00001)
        XCTAssertTrue(processor.supported.load(ordering: .relaxed))
        XCTAssertGreaterThan(processor.processedFrames.load(ordering: .relaxed), 0)
        XCTAssertNotNil(item.audioMix)
        let soughtEnd = await model.player.seek(to: CMTime(seconds: duration - 0.4, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        XCTAssertTrue(soughtEnd)
        model.player.play()
        for _ in 0..<160 {
            if model.queue.index == 1 && !model.preparing { break }
            try await Task.sleep(for: .milliseconds(250))
        }
        XCTAssertEqual(model.queue.index, 1)
        XCTAssertEqual(model.current?.id, ids[1])
        XCTAssertNil(model.error)
        XCTAssertEqual(model.player.currentItem?.status, .readyToPlay)
        XCTAssertNotNil(model.normalization, "Automatic next must install the next video's normalization.")
    }
}
