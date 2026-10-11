import Foundation
import Observation

struct LibraryStatus: Decodable, Equatable, Sendable {
    let revision: Int
    let total: Int
}

enum LibraryEvent: Equatable, Sendable {
    case snapshot(LibraryStatus)
    case changed(LibraryStatus)
    case artwork(String)
}
enum EventStreamError: Error { case unavailable }

// Parse complete frames, including comments, CRLF and multiline JSON. Never
// publish an incomplete frame when a connection disappears halfway through it.
struct EventDecoder {
    private var event = ""
    private var data: [String] = []
    private var size = 0
    mutating func append(_ line: String) throws -> LibraryEvent? {
        if line.isEmpty {
            defer { event = ""; data = []; size = 0 }
            guard !data.isEmpty else { return nil }
            let payload = Data(data.joined(separator: "\n").utf8)
            let decoder = JSONDecoder()
            switch event {
            case "snapshot": return .snapshot(try decoder.decode(LibraryStatus.self, from: payload))
            case "library-changed": return .changed(try decoder.decode(LibraryStatus.self, from: payload))
            case "artwork-ready":
                struct Artwork: Decodable { let artist: String }
                return .artwork(try decoder.decode(Artwork.self, from: payload).artist)
            default: return nil
            }
        }
        if line.hasPrefix(":") { return nil }
        let fields = line.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        let value = fields.count > 1 ? String(fields[1].dropFirst(fields[1].first == " " ? 1 : 0)) : ""
        if fields[0] == "event" { event = value }
        if fields[0] == "data" {
            size += value.utf8.count
            guard size <= 65536 else { throw URLError(.dataLengthExceedsMaximum) }
            data.append(value)
        }
        return nil
    }
}

@MainActor @Observable final class LibrarySync {
    var status: LibraryStatus?
    private(set) var artworkEpoch = 0
    private(set) var artworkCompletion = 0
    private var artworkVersions: [String: Int] = [:]
    private var streamConnected = false
    func artworkVersion(_ name: String) -> String {
        "\(artworkEpoch):\(artworkVersions[name.lowercased(), default: 0])"
    }
    func receive(_ event: LibraryEvent) {
        switch event {
        case .snapshot(let status):
            self.status = status
            artworkEpoch += 1
            artworkVersions.removeAll()
        case .changed(let status): self.status = status
        case .artwork(let name):
            artworkVersions[name.lowercased(), default: 0] += 1
            artworkCompletion += 1
        }
    }
    func monitor(api: API) async {
        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.poll(api: api) }
            group.addTask { await self.listen(api: api) }
            await group.waitForAll()
        }
    }
    private func poll(api: API) async {
        while !Task.isCancelled {
            do {
                let status: LibraryStatus = try await api.request("/api/status")
                try Task.checkCancellation()
                if self.status == nil || status.revision >= self.status!.revision { self.status = status }
                // One shared, infrequent recovery check for artwork if SSE is down.
                if !streamConnected { artworkEpoch += 1 }
                try await Task.sleep(for: .seconds(120))
            } catch {
                guard !Task.isCancelled else { return }
                do { try await Task.sleep(for: .seconds(120)) } catch { return }
            }
        }
    }
    private func listen(api: API) async {
        var delay = 2
        while !Task.isCancelled {
            do {
                try await api.events { event in self.streamConnected = true; self.receive(event); delay = 2 }
            } catch EventStreamError.unavailable {
                return // Older servers use the shared status polling fallback.
            } catch {
                streamConnected = false
                guard !Task.isCancelled else { return }
            }
            streamConnected = false
            do { try await Task.sleep(for: .seconds(delay)) } catch { return }
            delay = min(delay * 2, 60)
        }
    }
}
