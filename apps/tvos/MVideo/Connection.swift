import Foundation
import Security

struct Connection: Codable, Equatable {
    let origin: URL
    let token: String
    static func origin(_ input: String) throws -> URL {
        guard var c = URLComponents(string: input.trimmingCharacters(in: .whitespacesAndNewlines)),
              let host = c.host, !host.isEmpty, c.user == nil, c.password == nil,
              c.query == nil, c.fragment == nil, c.path.isEmpty || c.path == "/" else {
            throw ServiceError.message("Enter the server address without a path, account details or query.")
        }
        var allowed = c.scheme?.lowercased() == "https"
        #if DEBUG && targetEnvironment(simulator)
        allowed = allowed || (c.scheme == "http" && ["127.0.0.1", "localhost"].contains(host))
        #endif
        guard allowed else { throw ServiceError.message("Use the HTTPS address configured for your mvideo server.") }
        c.path = ""
        guard let url = c.url else { throw ServiceError.message("The server address is invalid.") }
        return url
    }
    func url(_ path: String, query: [URLQueryItem] = []) throws -> URL {
        guard path.hasPrefix("/"), !path.hasPrefix("//"), !path.contains("\\"),
              let relative = URLComponents(string: path), relative.host == nil, relative.scheme == nil,
              var c = URLComponents(url: origin, resolvingAgainstBaseURL: false) else {
            throw ServiceError.message("The server returned an invalid media address.")
        }
        c.percentEncodedPath = relative.percentEncodedPath
        let items = (relative.queryItems ?? []) + query
        c.queryItems = items.isEmpty ? nil : items
        guard let url = c.url else { throw ServiceError.message("The server returned an invalid address.") }
        return url
    }
}
enum ServiceError: LocalizedError {
    case message(String)
    var errorDescription: String? { switch self { case .message(let text): text } }
}
struct KeychainStore {
    private let service = "com.soundtrackgeek.mvideo"
    private var query: [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "server-session"] }
    func load() -> Connection? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return try? JSONDecoder().decode(Connection.self, from: data)
    }
    func save(_ connection: Connection) throws {
        let data = try JSONEncoder().encode(connection)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var request = query
            request[kSecValueData as String] = data
            request[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(request as CFDictionary, nil) == errSecSuccess else { throw ServiceError.message("Unable to save this session securely. Try again.") }
        } else if status != errSecSuccess { throw ServiceError.message("Unable to update the saved session.") }
    }
    func clear() { SecItemDelete(query as CFDictionary) }
}

private struct Failure: Decodable { let detail: String }

private final class OriginRedirectPolicy: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        guard let source = task.originalRequest?.url, let target = request.url,
              source.scheme == target.scheme, source.host == target.host,
              (source.port ?? 443) == (target.port ?? 443) else { completionHandler(nil); return }
        completionHandler(request)
    }
}

final class API: @unchecked Sendable {
    let connection: Connection
    private let session: URLSession
    init(_ connection: Connection) {
        self.connection = connection
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.httpCookieStorage = nil
        configuration.urlCache = nil
        session = URLSession(configuration: configuration, delegate: OriginRedirectPolicy(), delegateQueue: nil)
    }
    func request<T: Decodable>(_ path: String, query: [URLQueryItem] = [], method: String = "GET", body: Data? = nil) async throws -> T {
        var request = URLRequest(url: try connection.url(path, query: query))
        request.httpMethod = method
        request.httpBody = body
        request.setValue("Bearer \(connection.token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw ServiceError.message("The server did not respond.") }
        guard (200..<300).contains(response.statusCode) else {
            if response.statusCode == 401 { throw ServiceError.message("Your session has expired. Open Connection to pair again.") }
            let detail = (try? JSONDecoder().decode(Failure.self, from: data))?.detail
            throw ServiceError.message(detail ?? "The library is unavailable. Check the PC and Tailscale, then retry.")
        }
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
    func videos(scope: Scope, offset: Int = 0, revision: Int? = nil) async throws -> VideoPage {
        var query = scope.query + [.init(name: "offset", value: String(offset))]
        if let revision { query.append(.init(name: "revision", value: String(revision))) }
        return try await request("/api/videos", query: query)
    }
    func queue(scope: Scope, shuffle: Bool, start: String?) async throws -> QueueResponse {
        var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(scope)) as! [String: Any]
        object["shuffle"] = shuffle; object["start"] = start
        return try await request("/api/queue", method: "POST", body: JSONSerialization.data(withJSONObject: object))
    }
}
