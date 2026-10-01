import Foundation

struct Video: Codable, Identifiable, Hashable {
    let id: String
    let artist: String?
    let title: String
    let year: Int?
    let thumbnail: String?
    let warnings: [String]
    let probeError: String?
    var subtitle: String { [artist ?? "Artist unidentified", year.map(String.init)].compactMap { $0 }.joined(separator: " · ") }
}
struct VideoPage: Decodable {
    let items: [Video]
    let total: Int
    let nextOffset: Int?
    let revision: Int
}
struct Facet: Decodable, Identifiable, Hashable {
    let name: String
    let count: Int
    var id: String { name }
    enum CodingKeys: String, CodingKey { case name, count }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        count = try c.decode(Int.self, forKey: .count)
        if let string = try? c.decode(String.self, forKey: .name) { name = string }
        else { name = String(try c.decode(Int.self, forKey: .name)) }
    }
}
struct FacetPage: Decodable { let items: [Facet]; let total: Int; let nextOffset: Int? }
struct ArtistMetadata: Decodable {
    let state: String
    let biography: String?
    let sourceUrl: String?
    let images: [String]
    let attribution: String?
    let imageAttribution: String?
    let imageSourceUrl: String?
}
struct FeaturedArtwork: Decodable {
    let artist: String
    let image: String
    let attribution: String
    let sourceUrl: String
}
struct FeaturedResponse: Decodable { let item: FeaturedArtwork? }
struct PlaybackResponse: Decodable { let state: String; let mode: String; let url: String?; let error: String? }
struct QueueResponse: Decodable { let ids: [String]; let revision: Int }
struct Scope: Codable, Hashable {
    var q = ""
    var artist: String?
    var year: Int?
    var decade: Int?
    var unknown = false
    var field = "all"
    var query: [URLQueryItem] {
        var items = [URLQueryItem(name: "q", value: q), URLQueryItem(name: "field", value: field)]
        if let artist { items.append(.init(name: "artist", value: artist)) }
        if let year { items.append(.init(name: "year", value: String(year))) }
        if let decade { items.append(.init(name: "decade", value: String(decade))) }
        if unknown { items.append(.init(name: "unknown", value: "true")) }
        return items
    }
}
enum Page: Hashable {
    case home, search, artists, years, decades, artist(String), year(Int), decade(Int), unknown
    var title: String {
        switch self {
        case .home: "Your own music\ntelevision."
        case .search: "Find your next video"
        case .artists: "The artists you love."
        case .years: "Every year. Your story."
        case .decades: "A lifetime of music."
        case .artist(let name): name
        case .year(let year): String(year)
        case .decade(let decade): "The \(decade)s"
        case .unknown: "Year unconfirmed"
        }
    }
    var eyebrow: String {
        switch self {
        case .home: "FROM YOUR COLLECTION"
        case .artist: "ARTIST"
        case .year: "THE YEAR IN MUSIC VIDEOS"
        case .decade: "A DECADE OF MUSIC TELEVISION"
        default: "YOUR LIBRARY"
        }
    }
    var scope: Scope {
        switch self {
        case .artist(let name): Scope(artist: name)
        case .year(let year): Scope(year: year)
        case .decade(let decade): Scope(decade: decade)
        case .unknown: Scope(unknown: true)
        default: Scope()
        }
    }
    var facet: String? {
        switch self { case .artists: "artists"; case .years: "years"; case .decades: "decades"; default: nil }
    }
    var shuffleTitle: String {
        switch self {
        case .home: "Shuffle all"
        case .search: "Shuffle results"
        case .artist: "Shuffle artist"
        case .year(let year): "Shuffle \(year)"
        case .decade(let decade): "Shuffle the \(decade)s"
        default: "Shuffle selection"
        }
    }
}
