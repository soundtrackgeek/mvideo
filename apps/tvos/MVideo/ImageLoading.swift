import Foundation
import Nuke

enum ArtworkLoader {
    static let pipeline = makePipeline()

    static func makePipeline(configuration: URLSessionConfiguration = .ephemeral,
                             cache: DataCache? = try? DataCache(name: "com.soundtrackgeek.mvideo.artwork")) -> ImagePipeline {
        let transport = configuration.copy() as! URLSessionConfiguration
        transport.urlCache = nil
        transport.httpCookieStorage = nil
        transport.urlCredentialStorage = nil
        transport.timeoutIntervalForRequest = 30
        transport.timeoutIntervalForResource = 60
        transport.httpMaximumConnectionsPerHost = 4
        let loader = DataLoader(configuration: transport)
        loader.delegate = OriginRedirectPolicy()
        var options = ImagePipeline.Configuration()
        options.dataLoader = loader
        let memory = ImageCache(costLimit: 64 * 1024 * 1024)
        memory.entryCostLimit = 0.25 // Keep 1080p hero images within the same budget.
        options.imageCache = memory
        cache?.sizeLimit = 256 * 1024 * 1024
        options.dataCache = cache
        options.dataCachePolicy = .storeOriginalData
        return ImagePipeline(configuration: options)
    }

    // Retain the entire signed URL as the cache key: it includes the server,
    // session, expiry and content version. Never share entries across pairings.
    static func sizedURL(_ url: URL, pixelWidth: CGFloat) -> URL {
        guard url.path.hasPrefix("/artwork/"), var parts = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return url }
        let width = pixelWidth <= 640 ? 640 : pixelWidth <= 1280 ? 1280 : 1920
        var query = (parts.queryItems ?? []).filter { $0.name != "width" }
        query.append(.init(name: "width", value: String(width)))
        parts.queryItems = query
        return parts.url ?? url
    }

    static func request(url: URL?, size: CGSize, scale: CGFloat, fit: Bool = false) -> ImageRequest? {
        guard let url, size.width > 0, size.height > 0 else { return nil }
        // Quantize layout noise so identical tile sizes reuse decoded images.
        let pixels = CGSize(width: ceil(size.width * scale / 16) * 16,
                            height: ceil(size.height * scale / 16) * 16)
        var request = ImageRequest(url: sizedURL(url, pixelWidth: pixels.width))
        request.thumbnail = .init(size: pixels, unit: .pixels, contentMode: fit ? .aspectFit : .aspectFill)
        if pixels.width > 1280 { request.priority = .high }
        return request
    }
}

struct ArtworkPrefetchKey: Equatable {
    let scope: Scope
    let offset: Int?
    let revision: Int?
    let active: Bool
}
