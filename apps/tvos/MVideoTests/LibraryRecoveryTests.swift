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
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
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
