import SwiftUI

struct LibraryShell: View {
    let api: API
    let session: AppSession
    @State private var tab = Page.home
    @State private var path: [Page] = []
    @State private var showConnection = false
    @State private var featured: FeaturedArtwork?
    @State private var requestedArtwork = false
    private let tabs: [(String, Page)] = [("Home", .home), ("Search", .search), ("Artists", .artists), ("Years", .years), ("Decades", .decades)]
    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                HStack(spacing: 24) {
                    Text("mvideo").font(.system(size: 38, weight: .bold)).fixedSize().padding(.trailing, 60)
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
                BrowseScreen(api: api, page: tab, featured: featured).id(tab)
            }
            .navigationDestination(for: Page.self) { page in BrowseScreen(api: api, page: page) }
            .background(Theme.background)
        }
        .foregroundStyle(Theme.ivory)
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
                Button("Disconnect and pair again") { Task { await session.disconnect(); showConnection = false } }.buttonStyle(PillStyle())
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
    var total = 0
    var nextOffset: Int?
    var revision: Int?
    var metadata: ArtistMetadata?
    var loading = false
    var error: String?
    var loadedScope: Scope?
    private var generation = UUID()
    func load(api: API, page: Page, scope: Scope, more: Bool = false) async {
        if more && loading { return }
        let generation = UUID(); self.generation = generation
        loading = true; error = nil
        if !more { videos = []; facets = []; nextOffset = nil; metadata = nil }
        do {
            if let kind = page.facet {
                let result: FacetPage = try await api.request("/api/facets/" + kind, query: [URLQueryItem(name: "q", value: scope.q), .init(name: "offset", value: String(more ? nextOffset ?? 0 : 0))])
                guard self.generation == generation, !Task.isCancelled else { return }
                facets = more ? facets + result.items : result.items
                total = result.total; nextOffset = result.nextOffset
            } else {
                let result = try await api.videos(scope: scope, offset: more ? nextOffset ?? 0 : 0, revision: more ? revision : nil)
                guard self.generation == generation, !Task.isCancelled else { return }
                videos = more ? videos + result.items : result.items
                total = result.total; nextOffset = result.nextOffset; revision = result.revision
            }
            loadedScope = scope; loading = false
            if case .artist(let name) = page, !more {
                let info: ArtistMetadata = try await api.request("/api/artist", query: [.init(name: "name", value: name)])
                guard self.generation == generation, !Task.isCancelled else { return }
                metadata = info
            }
        } catch {
            guard self.generation == generation, !Task.isCancelled else { return }
            self.error = error.localizedDescription; loading = false
        }
    }
}
struct BrowseScreen: View {
    let api: API
    let page: Page
    var featured: FeaturedArtwork? = nil
    @State private var model = BrowseModel()
    @State private var query = ""
    @State private var searchField = "all"
    @State private var player: PlayerModel?
    @State private var showingPlayer = false
    @State private var showingBiography = false
    @State private var gallery: ArtistPhotoSelection?
    @State private var launching = false
    @State private var playbackError: String?
    @State private var returnFocus: String?
    @State private var restoreCounter = 0
    @State private var scrollPosition = ScrollPosition()
    @State private var scrollOffset: CGFloat = 0
    @State private var returnOffset: CGFloat = 0
    @FocusState private var focus: String?
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
                    if model.loading && model.videos.isEmpty && model.facets.isEmpty { ProgressView("Loading your library…").padding(40) }
                    else if model.total == 0 && model.error == nil {
                        stateMessage(page == .search ? "No matching videos" : "Your collection is on its way", message: page == .search ? "Try another artist, song title or year." : "Scan the library on your PC, then refresh this page.", action: "Refresh") { reload() }
                    }
                    if page.facet != nil { facetGrid }
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
            .onScrollGeometryChange(for: CGFloat.self) { $0.contentOffset.y + $0.contentInsets.top } action: { _, offset in scrollOffset = offset }
            .onChange(of: restoreCounter) {
                if let returnFocus {
                    // The focus engine may scroll as the cover closes. Restore the saved offset after that update.
                    Task {
                        focus = returnFocus
                        try? await Task.sleep(for: .milliseconds(350))
                        scrollPosition.scrollTo(y: returnOffset)
                    }
                }
            }
        }
        .task(id: scope) {
            guard model.loadedScope != scope else { return }
            if page == .search || page.facet == "artists" { try? await Task.sleep(for: .milliseconds(350)) }
            guard !Task.isCancelled else { return }
            await model.load(api: api, page: page, scope: scope)
        }
        .fullScreenCover(isPresented: $showingPlayer, onDismiss: {
            player?.stop(); player = nil; restoreCounter += 1
        }) {
            if let player { PlaybackScreen(model: player) }
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
            if page.facet == nil && page != .search {
                GeometryReader { geometry in
                    Artwork(url: heroURL, fallbackURL: model.videos.first?.thumbnail.flatMap { try? api.connection.url($0) }).frame(width: geometry.size.width * 0.68, height: geometry.size.height)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    LinearGradient(stops: [.init(color: Theme.background, location: 0.1), .init(color: Theme.background.opacity(0.85), location: 0.36), .init(color: Theme.background.opacity(0.1), location: 1)], startPoint: .leading, endPoint: .trailing)
                    LinearGradient(colors: [.clear, Theme.background], startPoint: .center, endPoint: .bottom)
                }.clipped()
            }
            VStack(alignment: .leading, spacing: 20) {
                Text(page.eyebrow).font(.system(size: 17, weight: .medium)).tracking(5).foregroundStyle(Theme.amber)
                Text(page.title).font(.system(size: heroFontSize, weight: .bold)).lineSpacing(-5).lineLimit(2).minimumScaleFactor(0.65)
                    .frame(maxWidth: page == .home ? 900 : 1300, alignment: .leading)
                if page != .search {
                    Text("\(model.total.formatted()) \(page.facet == nil ? "videos in your library" : page.facet ?? "items")")
                        .font(.system(size: 28)).foregroundStyle(Theme.secondary)
                }
                if case .artist = page {
                    Text(model.metadata?.biography ?? "Biography will appear when this artist’s identity is verified on your server.")
                        .font(.system(size: 24)).foregroundStyle(Theme.secondary).lineLimit(2).frame(maxWidth: 850, alignment: .leading)
                }
                if page.facet == nil && page != .search { actions }
                if page == .home, let featured {
                    Text("\(featured.artist) · fanart.tv").font(.system(size: 17)).foregroundStyle(Theme.secondary)
                        .accessibilityIdentifier("home-artwork-credit")
                }
            }.padding(.vertical, page == .search ? 30 : 50)
        }.frame(minHeight: page == .search || page.facet != nil ? 220 : 480)
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
    private var search: some View {
        VStack(alignment: .leading, spacing: 24) {
            TextField("Search artist, song title or year", text: $query)
                .autocorrectionDisabled().textInputAutocapitalization(.never).accessibilityIdentifier("search-input")
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
                        }.buttonStyle(CardStyle()).focused($focus, equals: video.id).id(video.id).accessibilityIdentifier("video-" + video.id)
                        if page == .search, let artist = video.artist {
                            NavigationLink("Explore \(artist)", value: Page.artist(artist)).buttonStyle(NavigationStyle())
                        }
                    }
                }
            }.focusSection()
        }
    }
    private var facetGrid: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 24), count: 3), spacing: 26) {
            ForEach(model.facets) { facet in
                NavigationLink(value: facetPage(facet)) {
                    FacetCard(api: api, facet: facet, title: page == .decades ? "\(facet.name)s" : facet.name)
                }.buttonStyle(CardStyle()).accessibilityIdentifier("facet-" + facet.name)
            }
        }.focusSection()
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
    private func reload() { Task { await model.load(api: api, page: page, scope: scope) } }
    private func launch(shuffle: Bool, start: String?, origin: String) {
        guard !launching else { return }
        launching = true; playbackError = nil; returnFocus = origin; returnOffset = scrollOffset
        Task {
            do {
                let queue = try await api.queue(scope: scope, shuffle: shuffle, start: start)
                guard !queue.ids.isEmpty else { throw ServiceError.message("This selection is empty. Refresh the library and try again.") }
                player = PlayerModel(api: api, ids: queue.ids, title: page == .home ? "Your collection" : page.title)
                showingPlayer = true
            } catch { playbackError = error.localizedDescription }
            launching = false
        }
    }
}
