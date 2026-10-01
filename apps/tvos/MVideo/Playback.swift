import AVKit
import SwiftUI

struct QueueCursor: Equatable {
    let ids: [String]
    private(set) var index = 0
    var current: String? { ids.indices.contains(index) ? ids[index] : nil }
    var hasPrevious: Bool { index > 0 }
    var hasNext: Bool { index + 1 < ids.count }
    mutating func next() { if index < ids.count { index += 1 } }
    mutating func previous() { index = max(0, index - 1) }
    mutating func restart() { index = 0 }
    mutating func move(to value: Int) { if ids.indices.contains(value) { index = value } }
}
@MainActor @Observable final class PlayerModel {
    let api: API
    let title: String
    let player = AVPlayer()
    var queue: QueueCursor
    var current: Video?
    var preparing = true
    var message = "Preparing your video…"
    var error: String?
    var finished = false
    var upNext: [Video] = []
    private var loadTask: Task<Void, Never>?
    private var previewTask: Task<Void, Never>?
    private var observation: NSKeyValueObservation?
    private var endObserver: NSObjectProtocol?
    private var failedObserver: NSObjectProtocol?
    init(api: API, ids: [String], title: String) {
        self.api = api; self.title = title; queue = QueueCursor(ids: ids)
    }
    func start() {
        loadTask?.cancel(); previewTask?.cancel(); clearObservers()
        player.pause(); player.replaceCurrentItem(with: nil)
        error = nil; current = nil; upNext = []; preparing = true; finished = queue.current == nil
        guard let id = queue.current else { preparing = false; return }
        let index = queue.index
        loadTask = Task { [weak self] in
            guard let self else { return }
            do {
                current = try await api.request("/api/videos/" + id)
                var prepared: PlaybackResponse?
                for _ in 0..<1800 {
                    try Task.checkCancellation()
                    let value: PlaybackResponse = try await api.request("/api/playback/" + id, method: "POST")
                    if value.state == "ready" { prepared = value; break }
                    if value.state == "error" { throw ServiceError.message(value.error ?? "This video couldn’t be prepared.") }
                    message = value.state == "busy" ? "Waiting for the server…" : "Preparing this video for Apple TV…"
                    try await Task.sleep(for: .seconds(2))
                }
                try Task.checkCancellation()
                guard queue.index == index, let path = prepared?.url else { throw ServiceError.message("Preparation took too long. Retry or skip this video.") }
                let item = AVPlayerItem(url: try api.connection.url(path))
                var metadata: [AVMetadataItem] = []
                for (identifier, value) in [(AVMetadataIdentifier.commonIdentifierTitle, current?.playbackTitle ?? ""), (.commonIdentifierArtist, current?.artist ?? "")] {
                    let field = AVMutableMetadataItem(); field.identifier = identifier; field.value = value as NSString; field.extendedLanguageTag = "und"; metadata.append(field)
                }
                item.externalMetadata = metadata
                observation = item.observe(\.status, options: [.new, .initial]) { [weak self] item, _ in
                    let status = item.status
                    Task { @MainActor in
                        guard let self, self.queue.index == index else { return }
                        if status == .readyToPlay { self.preparing = false }
                        if status == .failed { self.preparing = false; self.error = "Playback failed. Check the connection, then retry or skip this video." }
                    }
                }
                endObserver = NotificationCenter.default.addObserver(forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main) { [weak self] _ in
                    Task { @MainActor in self?.next() }
                }
                failedObserver = NotificationCenter.default.addObserver(forName: AVPlayerItem.failedToPlayToEndTimeNotification, object: item, queue: .main) { [weak self] _ in
                    Task { @MainActor in self?.error = "Playback was interrupted. Retry this video or skip to the next one."; self?.preparing = false }
                }
                player.replaceCurrentItem(with: item)
                try AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
                try AVAudioSession.sharedInstance().setActive(true)
                player.play()
                prefetch()
            } catch {
                guard !Task.isCancelled, queue.index == index else { return }
                self.error = error.localizedDescription; preparing = false
            }
        }
    }
    func next() { queue.next(); start() }
    func previous() { if player.currentTime().seconds > 3 { player.seek(to: .zero) } else { queue.previous(); start() } }
    func replay() { queue.restart(); start() }
    func select(_ id: String) { if let index = queue.ids.firstIndex(of: id) { queue.move(to: index); start() } }
    func stop() {
        loadTask?.cancel(); previewTask?.cancel(); clearObservers()
        player.pause(); player.replaceCurrentItem(with: nil)
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
    private func clearObservers() {
        observation = nil
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }; endObserver = nil
        if let failedObserver { NotificationCenter.default.removeObserver(failedObserver) }; failedObserver = nil
    }
    private func prefetch() {
        let ids = Array(queue.ids.dropFirst(queue.index + 1).prefix(8))
        previewTask = Task { [weak self] in
            guard let self else { return }
            var previews: [Video] = []
            for id in ids {
                guard !Task.isCancelled else { return }
                if let value: Video = try? await api.request("/api/videos/" + id) { previews.append(value) }
            }
            guard !Task.isCancelled else { return }
            upNext = previews
            if let id = ids.first { let _: PlaybackResponse? = try? await api.request("/api/playback/" + id, method: "POST") }
        }
    }
}
struct PlaybackScreen: View {
    @Bindable var model: PlayerModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ZStack {
            NativePlayer(model: model).ignoresSafeArea()
            if model.preparing || model.error != nil || model.finished {
                Color.black.opacity(0.85).ignoresSafeArea()
                VStack(spacing: 24) {
                    Text(model.finished ? "That was your selection." : model.current?.playbackTitle ?? model.title).font(.title.bold())
                    if model.preparing { ProgressView(model.message) }
                    if let error = model.error { Text(error).multilineTextAlignment(.center).frame(maxWidth: 950) }
                    if model.finished {
                        Text("Every video has had its turn.").foregroundStyle(Theme.secondary)
                        Button("Play again") { model.replay() }.buttonStyle(PillStyle())
                    }
                    HStack(spacing: 25) {
                        if model.error != nil { Button("Retry") { model.start() }.buttonStyle(PillStyle()) }
                        if model.queue.hasNext { Button("Skip video") { model.next() }.buttonStyle(PillStyle()) }
                        Button("Back to library") { dismiss() }.buttonStyle(PillStyle())
                    }
                }.foregroundStyle(Theme.ivory)
            }
        }.accessibilityIdentifier("playback-screen")
            .onExitCommand { dismiss() }
            .task { model.start() }.onDisappear { model.stop() }
    }
}
struct NativePlayer: UIViewControllerRepresentable {
    let model: PlayerModel
    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let controller = AVPlayerViewController()
        controller.player = model.player
        controller.videoGravity = .resizeAspect
        controller.showsPlaybackControls = true
        return controller
    }
    func updateUIViewController(_ controller: AVPlayerViewController, context: Context) {
        controller.transportBarCustomMenuItems = [
            UIAction(title: "Previous video", image: UIImage(systemName: "backward.end.fill")) { _ in model.previous() },
            UIAction(title: "Next video", image: UIImage(systemName: "forward.end.fill")) { _ in model.next() }
        ]
        let queue = UIHostingController(rootView: UpNextView(model: model))
        queue.title = "Up Next"
        queue.preferredContentSize = CGSize(width: 1400, height: 480)
        controller.customInfoViewControllers = [queue]
    }
}
struct UpNextView: View {
    @Bindable var model: PlayerModel
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("\(model.queue.index + 1) of \(model.queue.ids.count) · \(model.title)").font(.title3.bold())
            ScrollView(.horizontal) {
                HStack(spacing: 25) {
                    ForEach(model.upNext) { video in
                        Button { model.select(video.id) } label: {
                            VStack(alignment: .leading, spacing: 10) {
                                Artwork(url: video.thumbnail.flatMap { try? model.api.connection.url($0) }).frame(width: 320, height: 180)
                                Text(video.title).font(.system(size: 24)).lineLimit(1)
                                Text(video.artist ?? "Artist unidentified").foregroundStyle(Theme.secondary).lineLimit(1)
                            }.frame(width: 320)
                        }.buttonStyle(CardStyle())
                    }
                }.padding(15)
            }
        }.padding(35)
    }
}
