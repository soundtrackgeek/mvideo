import SwiftUI
import Nuke

struct LibraryShell: View {
    let api: API
    let session: AppSession
    @State private var tab = Page.home
    @State private var path: [Page] = []
    @State private var showConnection = false
    @State private var featured: FeaturedArtwork?
    @State private var requestedArtwork = false
    @State private var playback = PlaybackSession()
    @State private var sync = LibrarySync()
    @Environment(\.scenePhase) private var scenePhase
    private let tabs: [(String, Page)] = [("Home", .home), ("Search", .search), ("Playlists", .playlists), ("Artists", .artists), ("Years", .years), ("Decades", .decades)]
    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                HStack(spacing: 24) {
                    Text("mvideo").font(.system(size: 38, weight: .bold)).fixedSize().padding(.trailing, 24)
                    ForEach(tabs, id: \.0) { label, page in
                        Button { tab = page } label: {
                            VStack(spacing: 9) {
                                Text(label)
                                Capsule().fill(tab == page ? Theme.amber : .clear).frame(height: 3)
                            }
                        }.buttonStyle(NavigationStyle()).accessibilityIdentifier("nav-" + label.lowercased())
                    }
                    Spacer()
                    Button { showConnection = true } label: { Image(systemName: "network") }.buttonStyle(NavigationStyle()).accessibilityLabel("Connection")
                }.padding(.horizontal, 70).padding(.top, 35).padding(.bottom, 15).focusSection()
                BrowseScreen(api: api, page: tab, featured: featured, isCurrentPage: path.isEmpty).id(tab)
            }
            .navigationDestination(for: Page.self) { page in BrowseScreen(api: api, page: page, isCurrentPage: path.last == page) }
            .background(Theme.background)
        }
        .foregroundStyle(Theme.ivory)
        .environment(playback)
        .environment(sync)
        .task(id: scenePhase) {
            if scenePhase == .active { await sync.monitor(api: api) }
        }
        .disabled(playback.isFullScreen)
        .accessibilityHidden(playback.isFullScreen)
        .overlay(alignment: .bottomTrailing) {
            if let model = playback.model {
                PlaybackScreen(model: model, session: playback, browseBack: path.isEmpty ? nil : {
                    if !path.isEmpty { path.removeLast() }
                })
                    .id(ObjectIdentifier(model))
            }
        }
        .onChange(of: playback.artistToOpen) { _, artist in
            guard let artist else { return }
            let destination = Page.artist(artist)
            if path.last != destination { path.append(destination) }
            playback.artistToOpen = nil
        }
        .alert("Picture in Picture unavailable", isPresented: Binding(
            get: { playback.pictureInPictureError != nil },
            set: { if !$0 { playback.pictureInPictureError = nil } }
        )) {
            Button("OK") { playback.pictureInPictureError = nil }
        } message: {
            Text(playback.pictureInPictureError ?? "")
        }
        .task {
            guard !requestedArtwork else { return }
            requestedArtwork = true
            #if DEBUG && targetEnvironment(simulator)
            if let artist = ProcessInfo.processInfo.environment["MVIDEO_TEST_ARTIST"] { path = [.artist(artist)] }
            #endif
            // Choose once for this app session, preserving artwork when returning from playback or another tab.
            let response: FeaturedResponse? = try? await api.request("/api/featured")
            featured = response?.item
        }
        .sheet(isPresented: $showConnection) {
            VStack(spacing: 30) {
                Text("Your library connection").font(.title.bold())
                Text(api.connection.origin.absoluteString).foregroundStyle(Theme.secondary)
                Text("The PC and this Apple TV need an active Tailscale connection.")
                Button("Disconnect and pair again") { playback.stop(); Task { await session.disconnect(); showConnection = false } }.buttonStyle(PillStyle())
                Button("Close") { showConnection = false }.buttonStyle(PillStyle())
            }.padding(70)
        }
    }
}
struct NavigationStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { Label(configuration: configuration) }
    private struct Label: View {
        let configuration: Configuration
        @Environment(\.isFocused) private var focused
        var body: some View {
            configuration.label.font(.system(size: 24, weight: .medium)).padding(12)
                .foregroundStyle(focused ? Theme.amber : Theme.ivory)
                .background(focused ? Color.white.opacity(0.10) : .clear, in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(focused ? Theme.ivory : .clear, lineWidth: 2))
        }
    }
}
@MainActor @Observable final class BrowseModel {
    var videos: [Video] = []
    var facets: [Facet] = []
    var playlists: [Playlist] = []
    var playlist: Playlist?
    var total = 0
    var nextOffset: Int?
    var revision: Int?
    var metadata: ArtistMetadata?
    var loading = false
    var error: String?
    var loadedScope: Scope?
    private var generation = UUID()
    var catalogTotal: Int?
    func updateMessage(_ status: LibraryStatus?) -> String? {
        guard let status, let revision, status.revision != revision else { return nil }
        let added = status.total - (catalogTotal ?? status.total)
        return added > 0 ? "\(added.formatted()) more videos · Refresh" : "Library updated · Refresh"
    }
    func load(api: API, page: Page, scope: Scope, more: Bool = false, preserving: Bool = false, additionalCount: Int = 0) async {
        if (more || preserving) && loading { return }
        let generation = UUID(); self.generation = generation
        loading = true; error = nil
        defer { if self.generation == generation { loading = false } }
        let targetCount = preserving ? max(videos.count, facets.count, 1) + max(additionalCount, 0) : 1
        if !more && !preserving {
            videos = []; facets = []; playlists = []; playlist = nil; nextOffset = nil
            metadata = nil; loadedScope = nil; total = 0; revision = nil; catalogTotal = nil
        }
        do {
            if page == .playlists {
                let status: LibraryStatus = try await api.request("/api/status")
                let result: PlaylistPage = try await api.request("/api/playlists")
                guard self.generation == generation, !Task.isCancelled else { return }
                playlists = result.items; total = result.items.count; revision = status.revision
                catalogTotal = status.total
            } else if let kind = page.facet {
                var items: [Facet] = []
                var offset = more ? nextOffset ?? 0 : 0
                var expected = more ? revision : nil
                var result: FacetPage
                repeat {
                    var query = [URLQueryItem(name: "q", value: scope.q), .init(name: "offset", value: String(offset))]
                    if let expected { query.append(.init(name: "revision", value: String(expected))) }
                    result = try await api.request("/api/facets/" + kind, query: query)
                    try Task.checkCancellation()
                    if let expected, let actual = result.revision, actual != expected {
                        throw ServiceError.message("Library changed; refresh this page again.")
                    }
                    expected = result.revision; items += result.items; offset = result.nextOffset ?? 0
                } while preserving && items.count < targetCount && result.nextOffset != nil
                guard self.generation == generation, !Task.isCancelled else { return }
                facets = more ? facets + items : items
                total = result.total; nextOffset = result.nextOffset; revision = result.revision
            } else {
                var items: [Video] = []
                var offset = more ? nextOffset ?? 0 : 0
                var expected = more ? revision : nil
                var result: VideoPage
                repeat {
                    result = try await api.videos(scope: scope, offset: offset, revision: expected)
                    try Task.checkCancellation()
                    expected = result.revision; items += result.items; offset = result.nextOffset ?? 0
                } while preserving && items.count < targetCount && result.nextOffset != nil
                var detail: Playlist?
                if let id = scope.playlist, !more { detail = try await api.request("/api/playlists/" + id) }
                guard self.generation == generation, !Task.isCancelled else { return }
                videos = more ? videos + items : items
                total = result.total; nextOffset = result.nextOffset; revision = result.revision
                if !more { playlist = detail }
                if page == .home { catalogTotal = result.total }
            }
            loadedScope = scope
            if case .artist(let name) = page, !more {
                await loadMetadata(api: api, name: name, generation: generation)
            }
        } catch {
            guard !(error is CancellationError), self.generation == generation, !Task.isCancelled else { return }
            self.error = error.localizedDescription
        }
    }
    func loadMetadata(api: API, name: String) async {
        await loadMetadata(api: api, name: name, generation: generation)
    }
    private func loadMetadata(api: API, name: String, generation: UUID) async {
        do {
            let info: ArtistMetadata = try await api.request("/api/artist", query: [
                .init(name: "name", value: name), .init(name: "background", value: "true")])
            guard self.generation == generation, !Task.isCancelled else { return }
            metadata = info
        } catch { /* Retain the current biography and scoped thumbnail. */ }
    }
}
struct BrowseScreen: View {
    let api: API
    let page: Page
    var featured: FeaturedArtwork? = nil
    var isCurrentPage = true
    @State private var model = BrowseModel()
    @State private var imagePrefetcher = ImagePrefetcher(pipeline: ArtworkLoader.pipeline, destination: .diskCache, maxConcurrentRequestCount: 2)
    @State private var prefetchOffset: Int?
    @Environment(\.displayScale) private var displayScale
    @State private var query = ""
    @State private var searchField = "all"
    @Environment(PlaybackSession.self) private var playback
    @Environment(LibrarySync.self) private var sync
    @State private var showingBiography = false
    @State private var gallery: ArtistPhotoSelection?
    @State private var launching = false
    @State private var playbackError: String?
    @State private var returnFocus: String?
    @State private var lastBrowseFocus: String?
    @State private var lastBrowseOffset: CGFloat = 0
    @State private var refreshTask: Task<Void, Never>?
    @State private var restoreCounter = 0
    @State private var scrollPosition = ScrollPosition()
    @State private var scrollOffset: CGFloat = 0
    @State private var returnOffset: CGFloat = 0
    @FocusState private var focus: String?
    @Environment(\.scenePhase) private var scenePhase
    private var scope: Scope {
        var result = page.scope; result.q = query; result.field = searchField; return result
    }
    private var heroURL: URL? {
        let path = (page == .home ? featured?.image : nil) ?? model.metadata?.images.first ?? model.videos.first?.thumbnail
        return path.flatMap { try? api.connection.url($0) }
    }
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 36) {
                    hero
                    if page == .search || page.facet == "artists" { search }
                    rails
                    if let error = model.error {
                        stateMessage("Library unavailable", message: error, action: "Retry") { reload() }
                    }
                    if let error = playbackError {
                        stateMessage("Couldn’t start playback", message: error, action: "Dismiss") { playbackError = nil }
                    }
                    if model.loading && model.videos.isEmpty && model.facets.isEmpty && model.playlists.isEmpty { ProgressView("Loading your library…").padding(40) }
                    else if model.total == 0 && model.error == nil {
                        stateMessage(page == .search ? "No matching videos" : (page == .playlists || scope.playlist != nil ? "Your next great mix" : "Your collection is on its way"), message: page == .search ? "Try another artist, song title or year." : (page == .playlists || scope.playlist != nil ? "Add videos in Playlist studio using your browser, then refresh here." : "Scan the library on your PC, then refresh this page."), action: "Refresh") { reload() }
                    }
                    if page == .playlists { playlistGrid }
                    else if page.facet != nil { facetGrid }
                    else { videoGrid }
                    if model.nextOffset != nil {
                        Button(model.loading ? "Loading…" : "Load more") { Task { await model.load(api: api, page: page, scope: scope, more: true) } }
                            .buttonStyle(PillStyle()).disabled(model.loading).accessibilityIdentifier("load-more")
                    }
                    if case .artist = page, let metadata = model.metadata, !metadata.images.isEmpty {
                        artistPhotos(metadata)
                    }
                }.padding(.horizontal, 70).padding(.bottom, 90)
            }
            .background(Theme.background)
            .scrollPosition($scrollPosition)
            .onScrollGeometryChange(for: CGFloat.self) { $0.contentOffset.y } action: { _, offset in
                scrollOffset = offset
                if focus == lastBrowseFocus { lastBrowseOffset = offset }
            }
            .onChange(of: restoreCounter) {
                if isCurrentPage, let returnFocus {
                    // Wait for the playback overlay to release focus and re-enable
                    // browsing, then restore the offset after the focus engine scrolls.
                    Task {
                        try? await Task.sleep(for: .milliseconds(100))
                        focus = returnFocus
                        try? await Task.sleep(for: .milliseconds(350))
                        scrollPosition.scrollTo(y: returnOffset)
                    }
                }
            }
            .overlay(alignment: .topTrailing) {
                if isCurrentPage, let message = model.updateMessage(sync.status) {
                    Button { refreshInPlace(proxy: proxy) } label: { Label(message, systemImage: "arrow.clockwise") }
                        .buttonStyle(PillStyle()).disabled(model.loading)
                        .focused($focus, equals: "library-refresh")
                        .accessibilityIdentifier("library-refresh")
                        .padding(.trailing, 70).padding(.top, 20)
                }
            }
        }
        .task(id: scope) {
            guard model.loadedScope != scope else { return }
            if page == .search || page.facet == "artists" { try? await Task.sleep(for: .milliseconds(350)) }
            guard !Task.isCancelled else { return }
            await model.load(api: api, page: page, scope: scope)
            if let status = sync.status, model.revision == status.revision { model.catalogTotal = status.total }
        }
        .task(id: artistArtworkVersion) {
            guard case .artist(let name) = page, model.loadedScope == scope else { return }
            await model.loadMetadata(api: api, name: name)
        }
        .task(id: prefetchKey) {
            imagePrefetcher.stopPrefetching()
            guard isCurrentPage, model.loadedScope == scope, let offset = prefetchKey.offset else { return }
            do {
                let paths: [String]
                if let kind = page.facet {
                    var query = scope.query + [URLQueryItem(name: "offset", value: String(offset))]
                    if let revision = model.revision { query.append(.init(name: "revision", value: String(revision))) }
                    let result: FacetPage = try await api.request("/api/facets/" + kind, query: query)
                    paths = result.items.compactMap { $0.image ?? $0.thumbnail }
                } else {
                    let result = try await api.videos(scope: scope, offset: offset, revision: model.revision)
                    paths = result.items.compactMap(\.thumbnail)
                }
                try Task.checkCancellation()
                // Grid width is bounded by its three-column layout. Prefetch to
                // disk without decoding and let visible requests take priority.
                let urls = paths.compactMap { try? api.connection.url($0) }
                    .map { ArtworkLoader.sizedURL($0, pixelWidth: 560 * displayScale) }
                imagePrefetcher.startPrefetching(with: urls)
            } catch { /* Prefetch failures never replace the usable page. */ }
        }
        .onChange(of: sync.status) { _, status in
            if let status, model.revision == status.revision { model.catalogTotal = status.total }
        }
        .onChange(of: focus) { _, value in
            if let value, value != "library-refresh",
               lastBrowseFocus == nil || model.videos.contains(where: { $0.id == value })
                || value.hasPrefix("facet-") || value.hasPrefix("playlist-") || value == "search-input" {
                lastBrowseFocus = value
                lastBrowseOffset = scrollOffset
            }
        }
        .onChange(of: isCurrentPage) { _, current in
            if !current { refreshTask?.cancel(); imagePrefetcher.stopPrefetching() }
        }
        .onDisappear { refreshTask?.cancel(); imagePrefetcher.stopPrefetching() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active && isCurrentPage && !model.loading && !playback.isFullScreen,
               model.error != nil || model.loadedScope != scope || page == .playlists || scope.playlist != nil { reload() }
        }
        .onChange(of: playback.dismissalCount) {
            if isCurrentPage { restoreCounter += 1 }
        }
        .onChange(of: playback.isFullScreen) { _, fullScreen in
            if fullScreen { focus = nil }
        }
        .sheet(isPresented: $showingBiography) { biography }
        .fullScreenCover(item: $gallery, onDismiss: { restoreCounter += 1 }) { selection in
            if let metadata = model.metadata {
                ArtistPhotoViewer(api: api, artist: page.title, metadata: metadata, initialIndex: selection.id)
            }
        }
    }
    private var hero: some View {
        ZStack(alignment: .leading) {
            if page.facet == nil && page != .search && page != .playlists {
                GeometryReader { geometry in
                    Artwork(url: heroURL, fallbackURL: model.videos.first?.thumbnail.flatMap { try? api.connection.url($0) }).frame(width: geometry.size.width * 0.68, height: geometry.size.height)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    LinearGradient(stops: [.init(color: Theme.background, location: 0.1), .init(color: Theme.background.opacity(0.85), location: 0.36), .init(color: Theme.background.opacity(0.1), location: 1)], startPoint: .leading, endPoint: .trailing)
                    LinearGradient(colors: [.clear, Theme.background], startPoint: .center, endPoint: .bottom)
                }.clipped()
            }
            VStack(alignment: .leading, spacing: 20) {
                Text(page.eyebrow).font(.system(size: 17, weight: .medium)).tracking(5).foregroundStyle(Theme.amber)
                Text(model.playlist?.name ?? page.title).font(.system(size: heroFontSize, weight: .bold)).lineSpacing(-5).lineLimit(2).minimumScaleFactor(0.65)
                    .frame(maxWidth: page == .home ? 900 : 1300, alignment: .leading)
                if page != .search {
                    Text("\(model.total.formatted()) \(page == .playlists ? "playlists" : (scope.playlist != nil ? "available videos" : (page.facet == nil ? "videos in your library" : page.facet ?? "items")))")
                        .font(.system(size: 28)).foregroundStyle(Theme.secondary)
                }
                if let playlist = model.playlist {
                    Text(playlist.description).font(.system(size: 24)).foregroundStyle(Theme.secondary).lineLimit(3).frame(maxWidth: 1000, alignment: .leading)
                    if playlist.count > playlist.availableCount {
                        Text("\(playlist.count - playlist.availableCount) unavailable videos will be skipped.").font(.system(size: 21)).foregroundStyle(Theme.amber)
                    }
                }
                if page == .playlists {
                    Text("Create and edit in your browser: \(api.connection.origin.absoluteString)/studio/").font(.system(size: 22)).foregroundStyle(Theme.secondary)
                    Button("Refresh playlists") { reload() }.buttonStyle(PillStyle()).accessibilityIdentifier("refresh-playlists")
                }
                if case .artist = page {
                    Text(model.metadata?.biography ?? (model.metadata?.pending == true ? "Finding artist photos and biography…" : "Artist information is unavailable for this match."))
                        .font(.system(size: 24)).foregroundStyle(Theme.secondary).lineLimit(2).frame(maxWidth: 850, alignment: .leading)
                }
                if page.facet == nil && page != .search && page != .playlists { actions }
                if page == .home, let featured {
                    Text("\(featured.artist) · fanart.tv").font(.system(size: 17)).foregroundStyle(Theme.secondary)
                        .accessibilityIdentifier("home-artwork-credit")
                }
            }.padding(.vertical, page == .search ? 30 : 50)
        }.frame(minHeight: page == .search || page.facet != nil || page == .playlists ? 220 : 480)
    }
    private var heroFontSize: CGFloat { if case .year = page { return 142 }; return page == .home ? 84 : 78 }
    private var actions: some View {
        HStack(spacing: 24) {
            Button { launch(shuffle: true, start: nil, origin: "shuffle") } label: { Label(launching ? "Preparing…" : page.shuffleTitle, systemImage: "shuffle") }
                .focused($focus, equals: "shuffle").id("shuffle").accessibilityIdentifier("shuffle")
            Button { launch(shuffle: false, start: nil, origin: "play-all") } label: { Label("Play all", systemImage: "play.fill") }
                .focused($focus, equals: "play-all").id("play-all")
            if page == .home {
                if let featured { NavigationLink("Explore \(featured.artist)", value: Page.artist(featured.artist)) }
                else { NavigationLink("Browse artists", value: Page.artists) }
            }
            if case .artist = page { Button("Biography") { showingBiography = true } }
        }.buttonStyle(PillStyle()).disabled(model.total == 0 || launching).focusSection()
    }
    private var playlistGrid: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 26), count: 3), spacing: 32) {
            ForEach(model.playlists) { playlist in
                NavigationLink(value: Page.playlist(playlist.id, playlist.name)) {
                    VStack(alignment: .leading, spacing: 14) {
                        Color.clear.aspectRatio(16 / 9, contentMode: .fit)
                            .overlay { Artwork(url: playlist.thumbnail.flatMap { try? api.connection.url($0) }) }
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                        Text(playlist.name).font(.system(size: 27, weight: .semibold)).lineLimit(2)
                        Text("\(playlist.availableCount) videos").font(.system(size: 21)).foregroundStyle(Theme.secondary)
                        Text(playlist.description).font(.system(size: 20)).foregroundStyle(Theme.secondary).lineLimit(2)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(CardStyle()).focused($focus, equals: "playlist-" + playlist.id).id("playlist-" + playlist.id).accessibilityIdentifier("playlist-" + playlist.id)
            }
        }.scrollTargetLayout().focusSection()
    }
    private var search: some View {
        VStack(alignment: .leading, spacing: 24) {
            TextField("Search artist, song title or year", text: $query)
                .autocorrectionDisabled().textInputAutocapitalization(.never).accessibilityIdentifier("search-input").focused($focus, equals: "search-input")
                .frame(maxWidth: 1200)
            if page == .search {
                HStack(spacing: 20) {
                    ForEach([("All", "all"), ("Artists", "artist"), ("Titles", "title"), ("Years", "year")], id: \.1) { label, value in
                        Button { searchField = value } label: { Text(label).foregroundStyle(searchField == value ? Theme.amber : Theme.ivory) }
                    }
                    Spacer()
                    Button { launch(shuffle: true, start: nil, origin: "search-shuffle") } label: { Label("Shuffle results", systemImage: "shuffle") }
                        .focused($focus, equals: "search-shuffle").id("search-shuffle").disabled(model.total == 0 || launching)
                }.buttonStyle(PillStyle()).focusSection()
                Text("\(model.total.formatted()) matching videos").foregroundStyle(Theme.secondary)
            }
        }
    }
    @ViewBuilder private var rails: some View {
        if scope.playlist != nil {
            Button("Refresh playlist") { reload() }.buttonStyle(PillStyle()).accessibilityIdentifier("refresh-playlist")
        }
        if case .year(let year) = page {
            ScrollView(.horizontal) {
                HStack(spacing: 18) {
                    ForEach((max(1888, year - 3)...min(2100, year + 3)).map { $0 }, id: \.self) { value in
                        NavigationLink(String(value), value: Page.year(value)).foregroundStyle(value == year ? Theme.amber : Theme.ivory)
                    }
                    NavigationLink("Explore the \((year / 10) * 10)s", value: Page.decade((year / 10) * 10))
                }.buttonStyle(PillStyle()).padding(12)
            }.focusSection()
        }
        if case .decade(let decade) = page {
            HStack {
                if decade > 1880 { NavigationLink("‹ \(decade - 10)s", value: Page.decade(decade - 10)) }
                Spacer()
                if decade < 2100 { NavigationLink("\(decade + 10)s ›", value: Page.decade(decade + 10)) }
            }.buttonStyle(PillStyle())
            Text("Choose a year").font(.title2.bold())
            ScrollView(.horizontal) {
                HStack(spacing: 18) {
                    ForEach(Array(decade..<(decade + 10)), id: \.self) { year in
                        NavigationLink(String(year), value: Page.year(year)).buttonStyle(PillStyle())
                    }
                }.padding(12)
            }.focusSection()
        }
        if page == .years { NavigationLink("Videos with an unconfirmed year", value: Page.unknown).buttonStyle(PillStyle()) }
    }
    private var videoGrid: some View {
        VStack(alignment: .leading, spacing: 20) {
            if !model.videos.isEmpty { Text(page == .home ? "From your collection" : "Music videos").font(.title2.bold()) }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 26), count: 3), alignment: .leading, spacing: 32) {
                ForEach(model.videos) { video in
                    VStack(alignment: .leading, spacing: 8) {
                        Button { launch(shuffle: false, start: video.id, origin: video.id) } label: {
                            VStack(alignment: .leading, spacing: 12) {
                                // Reserve the thumbnail's bounds before loading. Source aspect ratios
                                // must not expand a lazy grid row into the following section.
                                Color.clear.aspectRatio(16 / 9, contentMode: .fit)
                                    .overlay { Artwork(url: video.thumbnail.flatMap { try? api.connection.url($0) }) }
                                    .clipShape(RoundedRectangle(cornerRadius: 10))
                                Text(video.title).font(.system(size: 25, weight: .semibold)).lineLimit(1)
                                Text(video.subtitle).font(.system(size: 21)).foregroundStyle(Theme.secondary).lineLimit(1)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }.buttonStyle(CardStyle()).focused($focus, equals: video.id).accessibilityIdentifier("video-" + video.id)
                        if page == .search, let artist = video.artist {
                            NavigationLink("Explore \(artist)", value: Page.artist(artist)).buttonStyle(NavigationStyle())
                        }
                    }.id(video.id)
                        .onAppear {
                            if model.videos.suffix(6).contains(where: { $0.id == video.id }) { prefetchOffset = model.nextOffset }
                        }
                }
            }.scrollTargetLayout().focusSection()
        }
    }
    private var facetGrid: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 24), count: 3), spacing: 26) {
            ForEach(model.facets) { facet in
                NavigationLink(value: facetPage(facet)) {
                    FacetCard(api: api, facet: facet, title: page == .decades ? "\(facet.name)s" : facet.name,
                              artistName: page == .artists ? facet.name : nil)
                }.buttonStyle(CardStyle()).focused($focus, equals: "facet-" + facet.name).id("facet-" + facet.name).accessibilityIdentifier("facet-" + facet.name)
                    .onAppear {
                        if model.facets.suffix(6).contains(where: { $0.name == facet.name }) { prefetchOffset = model.nextOffset }
                    }
            }
        }.scrollTargetLayout().focusSection()
    }
    private var prefetchKey: ArtworkPrefetchKey {
        ArtworkPrefetchKey(scope: scope, offset: prefetchOffset == model.nextOffset ? prefetchOffset : nil,
                           revision: model.revision, active: isCurrentPage)
    }
    private func artistPhotos(_ metadata: ArtistMetadata) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Artist photos").font(.title2.bold()).accessibilityIdentifier("artist-photos-heading")
            ScrollView(.horizontal) {
                LazyHStack(spacing: 24) {
                    ForEach(Array(metadata.images.enumerated()), id: \.element) { index, path in
                        Button {
                            returnFocus = "photo-\(index)"; returnOffset = scrollOffset
                            gallery = ArtistPhotoSelection(id: index)
                        } label: {
                            Artwork(url: try? api.connection.url(path))
                                .frame(width: 460, height: 260).clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(CardStyle())
                        .focused($focus, equals: "photo-\(index)")
                        .accessibilityLabel("\(page.title), photo \(index + 1) of \(metadata.images.count)")
                        .accessibilityIdentifier("artist-photo-\(index)")
                    }
                }.padding(12)
            }.scrollClipDisabled().focusSection()
            Text(metadata.imageAttribution ?? "Artist images · fanart.tv").font(.system(size: 21)).foregroundStyle(Theme.secondary)
        }.padding(.top, 28)
    }
    private func facetPage(_ facet: Facet) -> Page {
        switch page { case .years: .year(Int(facet.name) ?? 0); case .decades: .decade(Int(facet.name) ?? 0); default: .artist(facet.name) }
    }
    private func stateMessage(_ title: String, message: String, action: String, perform: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(title).font(.title2.bold()); Text(message).foregroundStyle(Theme.secondary)
            Button(action, action: perform).buttonStyle(PillStyle())
        }.padding(35).frame(maxWidth: .infinity, alignment: .leading).background(.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 15))
    }
    private var biography: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Text(page.title).font(.largeTitle.bold())
                Text(model.metadata?.biography ?? "No verified biography is available for this artist yet.").font(.title3)
                if let info = model.metadata {
                    Text(info.attribution ?? "").foregroundStyle(Theme.amber)
                    if let source = info.sourceUrl { Text(source).font(.callout) }
                    if let source = info.imageSourceUrl { Text("Artist images · fanart.tv\n" + source).font(.callout) }
                }
                Button("Close") { showingBiography = false }.buttonStyle(PillStyle())
            }.padding(90)
        }
    }
    private var artistArtworkVersion: String {
        if case .artist(let name) = page {
            return sync.artworkVersion(name) + (model.metadata?.deferred == true ? ":deferred:\(sync.artworkCompletion)" : "")
        }
        return ""
    }
    private func refreshInPlace(proxy: ScrollViewProxy? = nil) {
        let savedFocus = focus == "library-refresh" ? lastBrowseFocus : focus
        let savedOffset = focus == "library-refresh" ? lastBrowseOffset : scrollOffset
        let savedScope = scope
        let previousIndex = savedFocus.flatMap { value in
            model.videos.firstIndex { $0.id == value } ?? model.facets.firstIndex { "facet-" + $0.name == value }
                ?? model.playlists.firstIndex { "playlist-" + $0.id == value }
        }
        refreshTask?.cancel()
        refreshTask = Task {
            await model.load(api: api, page: page, scope: savedScope, preserving: true,
                             additionalCount: (sync.status?.total ?? 0) - (model.catalogTotal ?? sync.status?.total ?? 0))
            guard !Task.isCancelled, scope == savedScope, isCurrentPage, !playback.isFullScreen, model.error == nil else { return }
            if let status = sync.status, model.revision == status.revision { model.catalogTotal = status.total }
            let retained = savedFocus.map { value in
                model.videos.contains { $0.id == value } || model.facets.contains { "facet-" + $0.name == value }
                    || model.playlists.contains { "playlist-" + $0.id == value }
                    || ["shuffle", "play-all", "search-shuffle", "search-input"].contains(value)
            } ?? false
            let nextFocus = retained ? savedFocus : (model.videos.first?.id ?? model.facets.first.map { "facet-" + $0.name }
                ?? model.playlists.first.map { "playlist-" + $0.id })
            let newIndex = nextFocus.flatMap { value in
                model.videos.firstIndex { $0.id == value } ?? model.facets.firstIndex { "facet-" + $0.name == value }
                    ?? model.playlists.firstIndex { "playlist-" + $0.id == value }
            }
            // Let the new lazy-grid rows mount and the disappearing pill release
            // focus. If insertions moved the card, preserve the browsing location
            // by bringing that same card into view instead of its old pixel offset.
            try? await Task.sleep(for: .milliseconds(100))
            guard !Task.isCancelled, scope == savedScope else { return }
            if newIndex != previousIndex, let nextFocus {
                if let proxy { proxy.scrollTo(nextFocus, anchor: .center) }
                else { scrollPosition.scrollTo(id: nextFocus, anchor: .center) }
                try? await Task.sleep(for: .milliseconds(100))
            }
            guard !Task.isCancelled, scope == savedScope else { return }
            focus = nextFocus
            try? await Task.sleep(for: .milliseconds(350))
            guard !Task.isCancelled, scope == savedScope, isCurrentPage, !playback.isFullScreen else { return }
            if newIndex == previousIndex { scrollPosition.scrollTo(y: savedOffset) }
        }
    }
    private func reload() { refreshInPlace() }
    private func launch(shuffle: Bool, start: String?, origin: String) {
        guard !launching else { return }
        launching = true; playbackError = nil; returnFocus = origin; returnOffset = scrollOffset
        Task {
            do {
                let queue = try await api.queue(scope: scope, shuffle: shuffle, start: start)
                guard !queue.ids.isEmpty else { throw ServiceError.message("This selection is empty. Refresh the library and try again.") }
                playback.play(PlayerModel(api: api, ids: queue.ids, title: page == .home ? "Your collection" : page.title))
            } catch { playbackError = error.localizedDescription }
            launching = false
        }
    }
}
