import XCTest
import Nuke
import UIKit
@testable import MVideo

@MainActor final class ImageLoadingTests: XCTestCase {
    override func tearDown() {
        ImageTestProtocol.reset()
        super.tearDown()
    }

    func testRenditionSelectionPreservesSignedAddressAndUsesDisplayScale() throws {
        let url = try XCTUnwrap(URL(string: "https://library.test/artwork/artist/0/session.expiry.signature?name=Bj%C3%B6rk&v=content"))
        for (points, scale, width) in [(300.0, 1.0, "640"), (460.0, 2.0, "1280"), (1400.0, 2.0, "1920")] {
            let request = try XCTUnwrap(ArtworkLoader.request(url: url, size: CGSize(width: points, height: 270), scale: scale))
            let actual = try XCTUnwrap(request.url)
            let query = try XCTUnwrap(URLComponents(url: actual, resolvingAgainstBaseURL: false)?.queryItems)
            XCTAssertEqual(actual.path, url.path)
            XCTAssertEqual(query.first(where: { $0.name == "name" })?.value, "Björk")
            XCTAssertEqual(query.first(where: { $0.name == "v" })?.value, "content")
            XCTAssertEqual(query.first(where: { $0.name == "width" })?.value, width)
            XCTAssertNotNil(request.thumbnail)
        }
        let thumbnail = try XCTUnwrap(URL(string: "https://library.test/image/video/ticket?v=version"))
        XCTAssertEqual(ArtworkLoader.sizedURL(thumbnail, pixelWidth: 640), thumbnail)
        XCTAssertNil(ArtworkLoader.request(url: url, size: .zero, scale: 2))
    }

    func testDownsamplingMemoryAndDiskReuseAcrossPipelines() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let cache = try DataCache(path: directory)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ImageTestProtocol.self]
        ImageTestProtocol.prepare(data: try makeJPEG())
        let pipeline = ArtworkLoader.makePipeline(configuration: configuration, cache: cache)
        let request = try XCTUnwrap(ArtworkLoader.request(url: URL(string: "https://library.test/image/one/session.ticket?v=one"),
                                                        size: CGSize(width: 320, height: 180), scale: 1))
        let first = try await pipeline.image(for: request)
        // 180 rounds to 192 pixels; aspect-fill keeps the source's 16:9 ratio.
        XCTAssertLessThanOrEqual(first.cgImage?.width ?? 0, 342)
        XCTAssertLessThanOrEqual(first.cgImage?.height ?? 0, 192)
        XCTAssertGreaterThan(first.cgImage?.width ?? 0, 0)
        _ = try await pipeline.image(for: request)
        XCTAssertEqual(ImageTestProtocol.count, 1)
        cache.flush()
        let second = ArtworkLoader.makePipeline(configuration: configuration, cache: try DataCache(path: directory))
        _ = try await second.image(for: request)
        XCTAssertEqual(ImageTestProtocol.count, 1, "A new pipeline must reuse the disk entry")
        let otherSession = try XCTUnwrap(ArtworkLoader.request(url: URL(string: "https://library.test/image/one/other-session.ticket?v=one"),
                                                             size: CGSize(width: 320, height: 180), scale: 1))
        _ = try await second.image(for: otherSession)
        XCTAssertEqual(ImageTestProtocol.count, 2, "Signed URLs from other sessions must use separate cache entries")
    }

    func testConcurrentLoadsCoalesceOneDownload() async throws {
        ImageTestProtocol.prepare(data: try makeJPEG())
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ImageTestProtocol.self]
        let pipeline = ArtworkLoader.makePipeline(configuration: configuration, cache: nil)
        let url = try XCTUnwrap(URL(string: "https://library.test/image/coalesced/ticket"))
        async let first = pipeline.image(for: url)
        async let second = pipeline.image(for: url)
        _ = try await (first, second)
        XCTAssertEqual(ImageTestProtocol.count, 1)
    }

    func testCancellationStopsImageTransport() async throws {
        let started = expectation(description: "Image request started")
        let stopped = expectation(description: "Image request cancelled")
        ImageTestProtocol.prepare(data: Data(), started: started, stopped: stopped)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ImageTestProtocol.self]
        let pipeline = ArtworkLoader.makePipeline(configuration: configuration, cache: nil)
        let task = Task { try await pipeline.image(for: URL(string: "https://library.test/image/cancel/ticket")!) }
        await fulfillment(of: [started], timeout: 3)
        task.cancel()
        do { _ = try await task.value; XCTFail("Cancelled image load completed") } catch { }
        await fulfillment(of: [stopped], timeout: 3)
    }

    private func makeJPEG() throws -> Data {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 1920, height: 1080)).image { context in
            UIColor.orange.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 1920, height: 1080))
        }
        return try XCTUnwrap(image.jpegData(compressionQuality: 0.8))
    }
}

private final class ImageTestProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var bytes = Data()
    private static var requests = 0
    private static var started: XCTestExpectation?
    private static var stopped: XCTestExpectation?
    static var count: Int { lock.withLock { requests } }
    static func prepare(data: Data, started: XCTestExpectation? = nil, stopped: XCTestExpectation? = nil) {
        lock.withLock { bytes = data; requests = 0; self.started = started; self.stopped = stopped }
    }
    static func reset() { prepare(data: Data()) }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let (data, started) = Self.lock.withLock { Self.requests += 1; return (Self.bytes, Self.started) }
        if let started { started.fulfill(); return }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": "image/jpeg"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { Self.lock.withLock { Self.stopped }?.fulfill() }
}
