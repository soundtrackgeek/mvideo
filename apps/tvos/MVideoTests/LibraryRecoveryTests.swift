import Foundation
import XCTest
@testable import MVideo

final class LibraryRecoveryTests: XCTestCase {
    @MainActor func testHomeRecoversAfterArtworkSucceedsAndVideosTimeOut() async throws {
        let artworkStarted = expectation(description: "Artwork request started")
        let videosStarted = expectation(description: "Videos request started")
        let fixture = RecoveryFixture { request, attempt in
            if request.url?.path == "/api/featured" {
                return .pending(artworkStarted)
            }
            return attempt == 1 ? .pending(videosStarted) : .response(200, Self.page)
        }
        defer { fixture.stop() }
        let api = fixture.api()
        let artwork = Task { () throws -> FeaturedResponse in try await api.request("/api/featured") }
        let model = BrowseModel()
        let load = Task { await model.load(api: api, page: .home, scope: Page.home.scope) }
        await fulfillment(of: [artworkStarted, videosStarted], timeout: 3)
        XCTAssertTrue(fixture.finishPending(where: { $0.url?.path == "/api/featured" }, with: .response(200,
            #"{"item":{"artist":"'Til Tuesday","image":"/artist-image","attribution":"fanart.tv","source_url":"https://fanart.tv"}}"#)))
        let featured = try await artwork.value
        XCTAssertEqual(featured.item?.artist, "'Til Tuesday")
        XCTAssertTrue(model.loading)

        XCTAssertTrue(fixture.finishPending(where: { $0.url?.path == "/api/videos" }, with: .failure(.timedOut)))
        await load.value

        XCTAssertEqual(model.videos.map(\.id), ["recovered"])
        XCTAssertEqual(model.total, 1)
        XCTAssertEqual(model.loadedScope, Page.home.scope)
        XCTAssertFalse(model.loading)
        XCTAssertNil(model.error)
        XCTAssertEqual(fixture.requests.filter { $0.url?.path == "/api/featured" }.count, 1)
        XCTAssertEqual(fixture.requests.filter { $0.url?.path == "/api/videos" }.count, 2)
        XCTAssertEqual(fixture.requests.last?.value(forHTTPHeaderField: "Authorization"), "Bearer recovery-test")
    }

    @MainActor func testExhaustedRecoveryShowsErrorAndManualRetryCanSucceed() async {
        let fixture = RecoveryFixture { _, attempt in
            attempt <= 2 ? .failure(.timedOut) : .response(200, Self.page)
        }
        defer { fixture.stop() }
        let api = fixture.api()
        let model = BrowseModel()

        await model.load(api: api, page: .home, scope: Page.home.scope)

        XCTAssertEqual(fixture.requests.count, 2, "Automatic recovery must stop after one retry.")
        XCTAssertFalse(model.loading)
        XCTAssertNotNil(model.error)
        XCTAssertNil(model.loadedScope)
        XCTAssertTrue(model.videos.isEmpty)

        await model.load(api: api, page: .home, scope: Page.home.scope)

        XCTAssertEqual(fixture.requests.count, 3)
        XCTAssertEqual(model.videos.map(\.id), ["recovered"])
        XCTAssertFalse(model.loading)
        XCTAssertNil(model.error)
        XCTAssertEqual(model.loadedScope, Page.home.scope)
    }

    @MainActor func testFailedRefreshDoesNotKeepPreviousSuccessfulScope() async {
        let fixture = RecoveryFixture { _, attempt in
            attempt == 1 ? .response(200, Self.page) : .failure(.timedOut)
        }
        defer { fixture.stop() }
        let api = fixture.api()
        let model = BrowseModel()
        await model.load(api: api, page: .home, scope: Page.home.scope)
        XCTAssertEqual(model.loadedScope, Page.home.scope)

        await model.load(api: api, page: .home, scope: Page.home.scope)

        XCTAssertNil(model.loadedScope, "An unsuccessful refresh must remain eligible for loading again.")
        XCTAssertFalse(model.loading)
        XCTAssertNotNil(model.error)
        XCTAssertTrue(model.videos.isEmpty)
    }

    func testLostConnectionRetriesTheSameReadIncludingQueryAndAuthentication() async throws {
        let fixture = RecoveryFixture { _, attempt in
            attempt == 1 ? .failure(.networkConnectionLost) : .response(200, Self.page)
        }
        defer { fixture.stop() }
        let result = try await fixture.api().videos(scope: Scope(q: "'Til Tuesday", year: 1985), offset: 200, revision: 7)

        XCTAssertEqual(result.items.map(\.id), ["recovered"])
        let requests = fixture.requests
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests.first?.url, requests.last?.url)
        XCTAssertEqual(requests.first?.httpMethod, "GET")
        XCTAssertEqual(requests.first?.allHTTPHeaderFields, requests.last?.allHTTPHeaderFields)
        let query = URLComponents(url: try XCTUnwrap(requests.last?.url), resolvingAgainstBaseURL: false)?.queryItems
        XCTAssertEqual(query?.first(where: { $0.name == "offset" })?.value, "200")
        XCTAssertEqual(query?.first(where: { $0.name == "revision" })?.value, "7")
        XCTAssertEqual(query?.first(where: { $0.name == "q" })?.value, "'Til Tuesday")
    }

    func testQueueAndPlaybackPreparationRecoverFromTransientConnectionFailures() async throws {
        let fixture = RecoveryFixture { request, attempt in
            if attempt == 1 { return .failure(.timedOut) }
            if request.url?.path == "/api/queue" {
                return .response(200, #"{"ids":["recovered"],"revision":7}"#)
            }
            return .response(200, #"{"state":"ready","mode":"direct","url":"/media/recovered"}"#)
        }
        defer { fixture.stop() }
        let api = fixture.api()

        let queue = try await api.queue(scope: Scope(year: 1985), shuffle: true, start: nil)
        let playback = try await api.playback("recovered")

        XCTAssertEqual(queue.ids, ["recovered"])
        XCTAssertEqual(playback.state, "ready")
        let requests = fixture.requests
        XCTAssertEqual(requests.map { $0.url?.path }, ["/api/queue", "/api/queue", "/api/playback/recovered", "/api/playback/recovered"])
        XCTAssertTrue(requests.allSatisfy { $0.httpMethod == "POST" })
    }

    func testOrdinaryWritesDoNotRetryTransientFailures() async {
        for method in ["POST", "PUT", "PATCH", "DELETE"] {
            for code in [URLError.Code.timedOut, .networkConnectionLost] {
                let fixture = RecoveryFixture { _, _ in .failure(code) }
                defer { fixture.stop() }
                do {
                    let _: VideoPage = try await fixture.api().request("/api/write", method: method, body: Data("{}".utf8))
                    XCTFail("Expected \(method) to report its connection failure.")
                } catch {
                    XCTAssertEqual((error as? URLError)?.code, code)
                }
                XCTAssertEqual(fixture.requests.count, 1, "Do not replay an ordinary \(method) after an ambiguous failure.")
            }
        }
    }

    func testAuthenticationDecodingTLSAndCancellationErrorsDoNotRetry() async {
        let failures: [RecoveryFixture.Step] = [
            .response(401, #"{"detail":"Unauthorized"}"#),
            .response(200, "not JSON"),
            .failure(.secureConnectionFailed),
            .failure(.cancelled)
        ]
        for failure in failures {
            let fixture = RecoveryFixture { _, _ in failure }
            defer { fixture.stop() }
            do {
                let _: VideoPage = try await fixture.api().request("/api/videos")
                XCTFail("Expected the original nonrecoverable failure.")
            } catch {
                switch failure {
                case .response(401, _):
                    XCTAssertTrue(error.localizedDescription.contains("pair again"))
                case .response:
                    XCTAssertTrue(error is DecodingError)
                case .failure(let code):
                    XCTAssertEqual((error as? URLError)?.code, code)
                case .pending:
                    XCTFail("Unexpected pending fixture.")
                }
            }
            XCTAssertEqual(fixture.requests.count, 1)
        }
    }

    @MainActor func testCancellingAnInFlightLoadClearsLoadingWithoutRetryOrError() async {
        let started = expectation(description: "Library request started")
        let fixture = RecoveryFixture { _, _ in .pending(started) }
        defer { fixture.stop() }
        let api = fixture.api()
        let model = BrowseModel()
        let load = Task { await model.load(api: api, page: .home, scope: Page.home.scope) }
        await fulfillment(of: [started], timeout: 3)
        XCTAssertTrue(model.loading)

        load.cancel()
        await load.value

        XCTAssertFalse(model.loading)
        XCTAssertNil(model.error)
        XCTAssertNil(model.loadedScope)
        XCTAssertEqual(fixture.requests.count, 1)
    }

    @MainActor func testOlderLoadCannotReplaceResultsOrClearNewerLoadingState() async {
        let oldStarted = expectation(description: "Older request started")
        let newStarted = expectation(description: "Newer request started")
        let fixture = RecoveryFixture { request, _ in
            .pending(Self.query(request) == "old" ? oldStarted : newStarted)
        }
        defer { fixture.stop() }
        let api = fixture.api()
        let model = BrowseModel()
        let oldLoad = Task { await model.load(api: api, page: .search, scope: Scope(q: "old")) }
        await fulfillment(of: [oldStarted], timeout: 3)
        let newLoad = Task { await model.load(api: api, page: .search, scope: Scope(q: "new")) }
        await fulfillment(of: [newStarted], timeout: 3)

        XCTAssertTrue(fixture.finishPending(where: { Self.query($0) == "old" }, with: .response(200, Self.page)))
        await oldLoad.value
        XCTAssertTrue(model.loading, "Finishing an obsolete request must not clear the newer request's loading state.")
        XCTAssertTrue(model.videos.isEmpty)
        XCTAssertNil(model.loadedScope)

        XCTAssertTrue(fixture.finishPending(where: { Self.query($0) == "new" }, with: .response(200, Self.page)))
        await newLoad.value
        XCTAssertEqual(model.loadedScope, Scope(q: "new"))
        XCTAssertEqual(model.videos.map(\.id), ["recovered"])
        XCTAssertFalse(model.loading)
        XCTAssertNil(model.error)
    }

    @MainActor func testRefreshRetainsLoadedPagesUntilAllNewPagesSucceed() async throws {
        let secondPageStarted = expectation(description: "Second refresh page started")
        let fixture = RecoveryFixture { request, attempt in
            let offset = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "offset" }?.value
            if offset == "1" { return .pending(secondPageStarted) }
            if attempt == 1 { return .response(200, Self.pageJSON(["old1", "old2"], total: 2, revision: 7)) }
            return .response(200, Self.pageJSON(["new1"], total: 2, revision: 8, next: 1))
        }
        defer { fixture.stop() }
        let api = fixture.api()
        let model = BrowseModel()
        await model.load(api: api, page: .home, scope: Scope())
        let refresh = Task { await model.load(api: api, page: .home, scope: Scope(), preserving: true) }
        await fulfillment(of: [secondPageStarted], timeout: 3)
        XCTAssertEqual(model.videos.map(\.id), ["old1", "old2"])
        XCTAssertEqual(model.revision, 7)
        XCTAssertTrue(model.loading)
        XCTAssertTrue(fixture.finishPending(where: { $0.url?.query?.contains("offset=1") == true },
            with: .response(200, Self.pageJSON(["new2"], total: 2, revision: 8))))
        await refresh.value
        XCTAssertEqual(model.videos.map(\.id), ["new1", "new2"])
        XCTAssertEqual(model.revision, 8)
        XCTAssertFalse(model.loading)
        XCTAssertNil(model.error)
        XCTAssertTrue(fixture.requests.last?.url?.query?.contains("revision=8") == true)
    }

    @MainActor func testFailedOrCancelledRefreshKeepsTheUsableSnapshotAndNotice() async {
        for cancel in [false, true] {
            let started = expectation(description: "Refresh started")
            let fixture = RecoveryFixture { _, attempt in
                attempt == 1 ? .response(200, Self.page) : .pending(started)
            }
            defer { fixture.stop() }
            let api = fixture.api()
            let model = BrowseModel()
            await model.load(api: api, page: .home, scope: Scope())
            let refresh = Task { await model.load(api: api, page: .home, scope: Scope(), preserving: true) }
            await fulfillment(of: [started], timeout: 3)
            if cancel { refresh.cancel() }
            else { XCTAssertTrue(fixture.finishPending(where: { _ in true }, with: .response(409, #"{"detail":"Library changed"}"#))) }
            await refresh.value
            XCTAssertEqual(model.videos.map(\.id), ["recovered"])
            XCTAssertEqual(model.loadedScope, Scope())
            XCTAssertEqual(model.revision, 7)
            XCTAssertFalse(model.loading)
            XCTAssertEqual(model.updateMessage(LibraryStatus(revision: 8, total: 13)), "12 more videos · Refresh")
            if cancel { XCTAssertNil(model.error) } else { XCTAssertNotNil(model.error) }
        }
    }

    @MainActor func testRefreshLoadsExtraPagesForNewInsertionsBeforeExistingFocus() async {
        let fixture = RecoveryFixture { request, attempt in
            if request.url?.query?.contains("offset=2") == true {
                return .response(200, Self.pageJSON(["old2"], total: 3, revision: 8))
            }
            if attempt == 1 { return .response(200, Self.pageJSON(["old1", "old2"], total: 2, revision: 7)) }
            return .response(200, Self.pageJSON(["inserted", "old1"], total: 3, revision: 8, next: 2))
        }
        defer { fixture.stop() }
        let api = fixture.api()
        let model = BrowseModel()
        await model.load(api: api, page: .home, scope: Scope())
        await model.load(api: api, page: .home, scope: Scope(), preserving: true, additionalCount: 1)
        XCTAssertEqual(model.videos.map(\.id), ["inserted", "old1", "old2"])
        XCTAssertNil(model.nextOffset)
    }

    @MainActor func testSharedSyncTargetsArtworkAndResynchronizesAfterReconnect() {
        let sync = LibrarySync()
        sync.receive(.snapshot(LibraryStatus(revision: 7, total: 100)))
        let band = sync.artworkVersion("Band")
        let other = sync.artworkVersion("Other")
        sync.receive(.artwork("BAND"))
        XCTAssertNotEqual(sync.artworkVersion("Band"), band)
        XCTAssertEqual(sync.artworkVersion("Other"), other)
        sync.receive(.changed(LibraryStatus(revision: 8, total: 112)))
        XCTAssertEqual(sync.status, LibraryStatus(revision: 8, total: 112))
        XCTAssertEqual(sync.artworkVersion("Other"), other)
        sync.receive(.snapshot(LibraryStatus(revision: 8, total: 112)))
        XCTAssertNotEqual(sync.artworkVersion("Other"), other)
        let model = BrowseModel()
        model.revision = 7; model.catalogTotal = 100
        XCTAssertEqual(model.updateMessage(sync.status), "12 more videos · Refresh")
        model.revision = 8
        model.catalogTotal = 112
        XCTAssertNil(model.updateMessage(sync.status))
        sync.receive(.changed(LibraryStatus(revision: 9, total: 112)))
        XCTAssertEqual(model.updateMessage(sync.status), "Library updated · Refresh")
    }

    func testEventDecoderHandlesCommentsMultilineDataAndUnknownEvents() throws {
        var decoder = EventDecoder()
        let lines = [": ping", "", "retry: 5000", "event: snapshot", "data: {", "data: \"revision\":7,\"total\":100}", ""]
        var events: [LibraryEvent] = []
        for line in lines { if let event = try decoder.append(line) { events.append(event) } }
        XCTAssertEqual(events, [.snapshot(LibraryStatus(revision: 7, total: 100))])
        XCTAssertNil(try decoder.append("event: future-event"))
        XCTAssertNil(try decoder.append("data: not-json"))
        XCTAssertNil(try decoder.append(""))
        XCTAssertNil(try decoder.append("event: artwork-ready"))
        XCTAssertNil(try decoder.append(#"data: {"artist":"Band"}"#))
        XCTAssertEqual(try decoder.append(""), .artwork("Band"))
        XCTAssertNil(try decoder.append("event: snapshot"))
        XCTAssertNil(try decoder.append("data: invalid"))
        XCTAssertThrowsError(try decoder.append(""))
        var bounded = EventDecoder()
        XCTAssertThrowsError(try bounded.append("data: " + String(repeating: "x", count: 65537)))
    }

    @MainActor func testNativeEventTransportUsesAuthenticationAndCompleteFrames() async throws {
        let fixture = RecoveryFixture { _, _ in .response(200,
            "event: snapshot\r\ndata: {\"revision\":7,\"total\":1}\r\n\r\n: ping\r\n\r\nevent: artwork-ready\r\ndata: {\"artist\":\"Band\"}\r\n\r\nevent: library-changed\ndata: {\"revision\":8,") }
        defer { fixture.stop() }
        var events: [LibraryEvent] = []
        try await fixture.api().events { events.append($0) }
        XCTAssertEqual(events, [.snapshot(LibraryStatus(revision: 7, total: 1)), .artwork("Band")])
        XCTAssertEqual(fixture.requests.first?.value(forHTTPHeaderField: "Authorization"), "Bearer recovery-test")
        XCTAssertEqual(fixture.requests.first?.value(forHTTPHeaderField: "Accept"), "text/event-stream")
    }

    @MainActor func testOlderServerUsesStatusFallbackAndMonitorCancels() async {
        let statusStarted = expectation(description: "Status fallback checked")
        let eventsStarted = expectation(description: "Events checked")
        let fixture = RecoveryFixture { request, _ in
            if request.url?.path == "/api/events" { eventsStarted.fulfill(); return .response(404, "{}") }
            statusStarted.fulfill()
            return .response(200, #"{"revision":7,"total":1}"#)
        }
        defer { fixture.stop() }
        let api = fixture.api()
        let sync = LibrarySync()
        let monitor = Task { await sync.monitor(api: api) }
        await fulfillment(of: [statusStarted, eventsStarted], timeout: 3)
        for _ in 0..<100 where sync.status == nil { await Task.yield() }
        monitor.cancel()
        await monitor.value
        XCTAssertEqual(sync.status, LibraryStatus(revision: 7, total: 1))
        XCTAssertEqual(fixture.requests.count, 2)
    }

    private static func pageJSON(_ ids: [String], total: Int, revision: Int, next: Int? = nil) -> String {
        let items = ids.map { ["id": $0, "title": $0, "warnings": []] as [String: Any] }
        let value: [String: Any] = ["items": items, "total": total, "revision": revision, "next_offset": next as Any? ?? NSNull()]
        return String(data: try! JSONSerialization.data(withJSONObject: value), encoding: .utf8)!
    }

    private static let page = #"{"items":[{"id":"recovered","artist":"'Til Tuesday","title":"Voices Carry","year":1985,"warnings":[]}],"total":1,"next_offset":null,"revision":7}"#

    private static func query(_ request: URLRequest) -> String? {
        request.url.flatMap { URLComponents(url: $0, resolvingAgainstBaseURL: false) }?.queryItems?.first(where: { $0.name == "q" })?.value
    }
}

// Each test owns a unique host and request history. The locked registry prevents
// simultaneous tests or URLSession callback queues from sharing mutable handlers.
private final class RecoveryFixture {
    enum Step {
        case response(Int, String)
        case failure(URLError.Code)
        case pending(XCTestExpectation)
    }

    private let host = UUID().uuidString.lowercased() + ".library-recovery.invalid"
    private let handler: (URLRequest, Int) -> Step
    private let lock = NSLock()
    private var history: [URLRequest] = []
    private var pending: [RecoveryURLProtocol] = []

    init(handler: @escaping (URLRequest, Int) -> Step) {
        self.handler = handler
        RecoveryURLProtocol.register(self, host: host)
    }

    var requests: [URLRequest] {
        lock.lock(); defer { lock.unlock() }
        return history
    }

    func api() -> API {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RecoveryURLProtocol.self]
        return API(Connection(origin: URL(string: "https://" + host)!, token: "recovery-test"), configuration: configuration)
    }

    func receive(_ transport: RecoveryURLProtocol) {
        let request = transport.request
        lock.lock()
        history.append(request)
        let attempt = history.filter { $0.url == request.url && $0.httpMethod == request.httpMethod }.count
        lock.unlock()
        let step = handler(request, attempt)
        if case .pending(let started) = step {
            lock.lock(); pending.append(transport); lock.unlock()
            started.fulfill()
        } else {
            transport.finish(step)
        }
    }

    func finishPending(where predicate: (URLRequest) -> Bool, with step: Step) -> Bool {
        lock.lock()
        guard let index = pending.firstIndex(where: { predicate($0.request) }) else { lock.unlock(); return false }
        let transport = pending.remove(at: index)
        lock.unlock()
        transport.finish(step)
        return true
    }

    func stop() {
        RecoveryURLProtocol.unregister(host: host)
        lock.lock(); let unfinished = pending; pending.removeAll(); lock.unlock()
        for transport in unfinished { transport.finish(.failure(.cancelled)) }
    }
}

private final class RecoveryURLProtocol: URLProtocol {
    private static let registryLock = NSLock()
    private static var registry: [String: RecoveryFixture] = [:]
    private let stateLock = NSLock()
    private var finished = false

    static func register(_ fixture: RecoveryFixture, host: String) {
        registryLock.lock(); defer { registryLock.unlock() }
        registry[host] = fixture
    }

    static func unregister(host: String) {
        registryLock.lock(); defer { registryLock.unlock() }
        registry.removeValue(forKey: host)
    }

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host?.hasSuffix(".library-recovery.invalid") == true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.registryLock.lock()
        let fixture = request.url?.host.flatMap { Self.registry[$0] }
        Self.registryLock.unlock()
        guard let fixture else { finish(.failure(.unsupportedURL)); return }
        fixture.receive(self)
    }

    override func stopLoading() {
        stateLock.lock(); finished = true; stateLock.unlock()
    }

    func finish(_ step: RecoveryFixture.Step) {
        stateLock.lock()
        guard !finished else { stateLock.unlock(); return }
        finished = true
        stateLock.unlock()
        switch step {
        case .response(let status, let body):
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": request.url?.path == "/api/events" ? "text/event-stream" : "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        case .failure(let code):
            client?.urlProtocol(self, didFailWithError: URLError(code))
        case .pending:
            preconditionFailure("Pending responses must be completed explicitly.")
        }
    }
}
