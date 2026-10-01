import XCTest
@testable import MVideo

final class CoreTests: XCTestCase {
    func testOriginDoesNotAcceptCredentialsOrPaths() throws {
        for origin in ["https://user:pass@example.com", "https://example.com/api", "https://example.com?q=1", "file:///tmp/a"] {
            XCTAssertThrowsError(try Connection.origin(origin))
        }
        XCTAssertEqual(try Connection.origin(" https://example.com:8443/ ").absoluteString, "https://example.com:8443")
    }
    func testMediaAlwaysStaysOnServer() throws {
        let connection = Connection(origin: try Connection.origin("https://example.com:8443"), token: "test")
        XCTAssertThrowsError(try connection.url("https://untrusted.example/video"))
        XCTAssertThrowsError(try connection.url("//untrusted.example/video"))
        let url = try connection.url("/artwork/one?name=Bj%C3%B6rk")
        XCTAssertEqual(url.host, "example.com")
        XCTAssertEqual(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first?.value, "Björk")
    }
    func testQueueExhaustionAndHistory() {
        var cursor = QueueCursor(ids: ["a", "b", "c"])
        XCTAssertEqual(cursor.current, "a")
        cursor.next(); XCTAssertEqual(cursor.current, "b")
        cursor.previous(); XCTAssertEqual(cursor.current, "a")
        cursor.next(); cursor.next(); cursor.next()
        XCTAssertNil(cursor.current)
        cursor.restart(); XCTAssertEqual(cursor.current, "a")
        cursor.move(to: 2); XCTAssertEqual(cursor.current, "c")
        cursor.move(to: 100); XCTAssertEqual(cursor.current, "c")
    }
    func testEmptyQueueAndScope() {
        XCTAssertNil(QueueCursor(ids: []).current)
        XCTAssertEqual(Page.year(1973).scope.year, 1973)
        XCTAssertEqual(Page.decade(2000).scope.decade, 2000)
        XCTAssertEqual(Page.artist("a-ha").scope.artist, "a-ha")
        XCTAssertTrue(Page.unknown.scope.unknown)
    }
    func testDecodeServerVideo() throws {
        let data = Data(#"{"id":"a","artist":"a-ha","title":"Take On Me","year":1985,"thumbnail":"/image/a/ticket","warnings":[],"probe_error":null}"#.utf8)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let video = try decoder.decode(Video.self, from: data)
        XCTAssertEqual(video.subtitle, "a-ha · 1985")
        XCTAssertEqual(video.playbackTitle, "a-ha - Take On Me (1985)")
    }
    func testPlaybackTitleWithIncompleteMetadata() throws {
        let unknown = Video(id: "a", artist: nil, title: "Unidentified song", year: nil, thumbnail: nil, warnings: [], probeError: nil)
        XCTAssertEqual(unknown.playbackTitle, "Unidentified song")
        let noYear = Video(id: "b", artist: "Prince", title: "1999", year: nil, thumbnail: nil, warnings: [], probeError: nil)
        XCTAssertEqual(noYear.playbackTitle, "Prince - 1999")
        let noArtist = Video(id: "c", artist: "", title: "Song", year: 1985, thumbnail: nil, warnings: [], probeError: nil)
        XCTAssertEqual(noArtist.playbackTitle, "Song (1985)")
    }
}
