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

// The library owns playback so navigation never replaces the player or its item.
@MainActor @Observable final class PlaybackSession {
    enum Presentation { case fullScreen, miniPlayer, systemPictureInPicture }
    private(set) var model: PlayerModel?
    private(set) var presentation = Presentation.fullScreen
    private(set) var dismissalCount = 0
    var artistToOpen: String?
    var pictureInPictureError: String?
    var isFullScreen: Bool { model != nil && presentation == .fullScreen }

    func play(_ model: PlayerModel) {
        self.model?.stop()
        self.model = model
        presentation = .fullScreen
        artistToOpen = nil
        pictureInPictureError = nil
        model.start()
    }
    func minimize() {
        guard model != nil else { return }
        presentation = .miniPlayer
        dismissalCount += 1
    }
    func showArtist() {
        guard let artist = model?.currentArtist else { return }
        artistToOpen = artist
        if presentation == .fullScreen { presentation = .miniPlayer }
    }
    func restore() {
        guard model != nil else { return }
        presentation = .fullScreen
    }
    func didStartPictureInPicture() {
        guard model != nil else { return }
        presentation = .systemPictureInPicture
        dismissalCount += 1
    }
    func didStopPictureInPicture() {
        // Restoration changes presentation first. Closing the system window ends playback.
        if presentation == .systemPictureInPicture { stop() }
    }
    func stop() {
        model?.stop()
        model = nil
        artistToOpen = nil
        presentation = .fullScreen
        dismissalCount += 1
    }
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
    var currentArtist: String? {
        guard let artist = current?.artist?.trimmingCharacters(in: .whitespacesAndNewlines), !artist.isEmpty else { return nil }
        return artist
    }
    private(set) var normalizationEnabled: Bool
    private(set) var normalizationMessage = "Original volume"
    private(set) var normalization: AudioNormalization?
    private let preferences: UserDefaults
    private var normalizationTask: Task<Void, Never>?
    private var loadID = UUID()
    private var loadTask: Task<Void, Never>?
    private var previewTask: Task<Void, Never>?
    private var observation: NSKeyValueObservation?
    private var endObserver: NSObjectProtocol?
    private var failedObserver: NSObjectProtocol?
    init(api: API, ids: [String], title: String, preferences: UserDefaults = .standard) {
        self.api = api; self.title = title; queue = QueueCursor(ids: ids)
        self.preferences = preferences
        normalizationEnabled = preferences.object(forKey: "normalizeVolume") as? Bool ?? true
    }
    func start() {
        loadTask?.cancel(); previewTask?.cancel(); normalizationTask?.cancel(); clearObservers()
        loadID = UUID()
        let generation = loadID
        // Retain the outgoing item while preparing its successor so system PiP
        // is not torn down by a transient empty player between queue entries.
        player.pause()
        normalization = nil
        normalizationMessage = "Original volume"
        error = nil; current = nil; upNext = []; preparing = true; finished = queue.current == nil
        guard let id = queue.current else { player.replaceCurrentItem(with: nil); preparing = false; return }
        let index = queue.index
        loadTask = Task { [weak self] in
            guard let self else { return }
            do {
                current = try await api.request("/api/videos/" + id)
                var prepared: PlaybackResponse?
                for _ in 0..<1800 {
                    try Task.checkCancellation()
                    let value = try await api.playback(id)
                    if value.state == "ready" { prepared = value; break }
                    if value.state == "error" { throw ServiceError.message(value.error ?? "This video couldn’t be prepared.") }
                    message = value.state == "busy" ? "Waiting for the server…" : "Preparing this video for Apple TV…"
                    try await Task.sleep(for: .seconds(2))
                }
                try Task.checkCancellation()
                guard queue.index == index, let path = prepared?.url else { throw ServiceError.message("Preparation took too long. Retry or skip this video.") }
                let item = AVPlayerItem(url: try api.connection.url(path))
                var adjustment: AudioNormalization?
                var volumeMessage = prepared?.normalization == nil
                    ? "Original volume · update the library server to enable normalization"
                    : "Original volume · no usable measurement"
                if let gain = prepared?.normalization?.gain {
                    do {
                        adjustment = try await AudioNormalization.make(for: item.asset, gain: gain, enabled: normalizationEnabled)
                        volumeMessage = "Checking volume normalization…"
                    } catch {
                        volumeMessage = "Original volume · normalization unavailable"
                    }
                }
                try Task.checkCancellation()
                guard loadID == generation else { return }
                normalization = adjustment
                normalization?.processor.enabled.store(normalizationEnabled, ordering: .relaxed)
                normalizationMessage = volumeMessage
                // Install before the item enters AVPlayer, avoiding an unadjusted opening burst.
                item.audioMix = adjustment?.mix
                var metadata: [AVMetadataItem] = []
                for (identifier, value) in [(AVMetadataIdentifier.commonIdentifierTitle, current?.playbackTitle ?? ""), (.commonIdentifierArtist, current?.artist ?? "")] {
                    let field = AVMutableMetadataItem(); field.identifier = identifier; field.value = value as NSString; field.extendedLanguageTag = "und"; metadata.append(field)
                }
                item.externalMetadata = metadata
                observation = item.observe(\.status, options: [.new, .initial]) { [weak self] item, _ in
                    let status = item.status
                    Task { @MainActor in
                        guard let self, self.loadID == generation else { return }
                        if status == .readyToPlay { self.preparing = false }
                        if status == .failed { self.preparing = false; self.error = "Playback failed. Check the connection, then retry or skip this video." }
                    }
                }
                endObserver = NotificationCenter.default.addObserver(forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main) { [weak self] _ in
                    Task { @MainActor in
                        guard let self, self.loadID == generation else { return }
                        self.next()
                    }
                }
                failedObserver = NotificationCenter.default.addObserver(forName: AVPlayerItem.failedToPlayToEndTimeNotification, object: item, queue: .main) { [weak self] _ in
                    Task { @MainActor in
                        guard let self, self.loadID == generation else { return }
                        self.error = "Playback was interrupted. Retry this video or skip to the next one."; self.preparing = false
                    }
                }
                player.replaceCurrentItem(with: item)
                try AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
                try AVAudioSession.sharedInstance().setActive(true)
                player.play()
                observeNormalization(generation: generation)
                prefetch()
            } catch {
                guard !Task.isCancelled, queue.index == index else { return }
                self.error = error.localizedDescription; preparing = false
            }
        }
    }
    func next() { queue.next(); start() }
    func previous() {
        guard queue.hasPrevious else { return }
        queue.previous(); start()
    }
    func replay() { queue.restart(); start() }
    func select(_ id: String) { if let index = queue.ids.firstIndex(of: id) { queue.move(to: index); start() } }
    func stop() {
        loadTask?.cancel(); previewTask?.cancel(); normalizationTask?.cancel(); clearObservers()
        loadID = UUID()
        player.pause(); player.replaceCurrentItem(with: nil)
        normalization = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
    func toggleNormalization() {
        normalizationEnabled.toggle()
        preferences.set(normalizationEnabled, forKey: "normalizeVolume")
        normalization?.processor.enabled.store(normalizationEnabled, ordering: .relaxed)
    }
    private func observeNormalization(generation: UUID) {
        guard let processor = normalization?.processor else { return }
        normalizationTask = Task { [weak self] in
            for _ in 0..<40 {
                do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
                guard let self, self.loadID == generation else { return }
                if processor.processedFrames.load(ordering: .relaxed) > 0 {
                    self.normalizationMessage = "Volume normalization on"
                    return
                }
            }
            guard let self, self.loadID == generation else { return }
            self.normalizationMessage = "Original volume · normalization unavailable"
        }
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
            if let id = ids.first { let _ = try? await api.playback(id) }
        }
    }
}
struct PlaybackScreen: View {
    let model: PlayerModel
    let session: PlaybackSession
    var browseBack: (() -> Void)?
    @FocusState private var expandFocused: Bool
    private var fullScreen: Bool { session.presentation == .fullScreen }
    private var systemPictureInPicture: Bool { session.presentation == .systemPictureInPicture }
    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 0) {
                ZStack {
                    // Keep this representable in the same structural position when resizing.
                    NativePlayer(model: model, session: session)
                        .allowsHitTesting(fullScreen)
                        .accessibilityHidden(!fullScreen)
                    if fullScreen && (model.preparing || model.error != nil || model.finished) {
                        playbackStatus
                    }
                }
                .frame(height: fullScreen ? geometry.size.height : 292.5)
                .opacity(systemPictureInPicture ? 0 : 1)
                .frame(height: systemPictureInPicture ? 0 : nil)
                .clipped()
                if !fullScreen { miniPlayerControls }
            }
            .frame(width: fullScreen ? geometry.size.width : 520)
            .background(.black)
            .clipShape(RoundedRectangle(cornerRadius: fullScreen ? 0 : 16))
            .overlay(RoundedRectangle(cornerRadius: fullScreen ? 0 : 16)
                .strokeBorder(fullScreen ? .clear : Theme.secondary.opacity(0.5), lineWidth: 1))
            .padding(fullScreen ? 0 : 45)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        }
        .ignoresSafeArea()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(fullScreen ? "playback-screen" : "mini-player")
        .accessibilityValue(model.finished ? "Selection finished" : "\(model.preparing ? "Preparing video" : "Video") \(model.queue.index + 1) of \(model.queue.ids.count)")
        .onExitCommand(perform: fullScreen ? { session.stop() } : browseBack)
        .onChange(of: fullScreen) { _, fullScreen in
            if !fullScreen && !systemPictureInPicture { expandFocused = true }
        }
    }
    private var playbackStatus: some View {
        ZStack {
            Color.black.opacity(0.85)
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
                    Button("Back to library") { session.stop() }.buttonStyle(PillStyle())
                }
            }.foregroundStyle(Theme.ivory)
        }
    }
    private var miniPlayerControls: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.current?.playbackTitle ?? model.title).font(.system(size: 22, weight: .semibold)).lineLimit(2)
            if model.finished || model.error != nil || model.preparing {
                Text(model.finished ? "Selection finished" : model.error ?? model.message)
                    .font(.system(size: 18)).foregroundStyle(Theme.secondary).lineLimit(2)
            } else if systemPictureInPicture {
                Text("Playing in Picture in Picture").font(.system(size: 18)).foregroundStyle(Theme.secondary)
            }
            if model.error != nil || model.finished {
                HStack {
                    if model.finished { Button("Play again") { model.replay() } }
                    if model.error != nil { Button("Retry") { model.start() } }
                    if model.queue.hasNext { Button("Skip video") { model.next() } }
                }.buttonStyle(NavigationStyle())
            }
            HStack(spacing: 16) {
                if !systemPictureInPicture {
                    Button { session.restore() } label: { Image(systemName: "arrow.up.left.and.arrow.down.right") }
                        .focused($expandFocused)
                        .accessibilityLabel("Return to full screen").accessibilityIdentifier("mini-player-expand")
                    Button {
                        if model.player.rate == 0 { model.player.play() } else { model.player.pause() }
                    } label: { Image(systemName: "playpause.fill") }
                        .disabled(model.preparing || model.finished || model.error != nil)
                        .accessibilityLabel("Play or pause").accessibilityIdentifier("mini-player-play-pause")
                }
                if model.currentArtist != nil {
                    Button { session.showArtist() } label: { Image(systemName: "person.crop.rectangle") }
                        .accessibilityLabel("Go to artist").accessibilityIdentifier("mini-player-artist")
                }
                Button { session.stop() } label: { Image(systemName: "xmark") }
                    .accessibilityLabel("Stop playback").accessibilityIdentifier("mini-player-stop")
            }.buttonStyle(NavigationStyle())
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .foregroundStyle(Theme.ivory)
        .focusSection()
    }
}
// Keep the playback context from finger-down: AVKit can reveal its controls
// during the same swipe, before UIKit recognizes the horizontal movement.
class PlaylistSwipeGestureRecognizer: UISwipeGestureRecognizer {
    var startingItem: AVPlayerItem?
    var startingIndex: Int?
    override func reset() {
        super.reset()
        startingItem = nil
        startingIndex = nil
    }
}

struct NativePlayer: UIViewControllerRepresentable {
    let model: PlayerModel
    let session: PlaybackSession
    func makeCoordinator() -> Coordinator { Coordinator(model: model, session: session) }
    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let controller = AVPlayerViewController()
        controller.player = model.player
        controller.videoGravity = .resizeAspect
        controller.showsPlaybackControls = true
        controller.allowsPictureInPicturePlayback = true
        controller.delegate = context.coordinator
        context.coordinator.controller = controller
        for gesture in context.coordinator.playlistGestures { controller.view.addGestureRecognizer(gesture) }
        return controller
    }
    func updateUIViewController(_ controller: AVPlayerViewController, context: Context) {
        context.coordinator.model = model
        let fullScreen = session.presentation == .fullScreen
        controller.showsPlaybackControls = fullScreen
        controller.view.isUserInteractionEnabled = fullScreen
        context.coordinator.updateFocus(fullScreen: fullScreen)
        for gesture in context.coordinator.playlistGestures {
            gesture.isEnabled = fullScreen && !model.preparing && model.error == nil && !model.finished
        }
        var actions: [UIMenuElement] = []
        if model.currentArtist != nil {
            actions.append(UIAction(title: "Go to artist", image: UIImage(systemName: "person.crop.rectangle")) { _ in session.showArtist() })
        }
        actions.append(UIAction(title: "Browse in mini player", image: UIImage(systemName: "pip.enter")) { _ in session.minimize() })
        controller.transportBarCustomMenuItems = actions + [
            UIAction(title: "Normalize volume", image: UIImage(systemName: "waveform"),
                     state: model.normalizationEnabled ? .on : .off) { _ in model.toggleNormalization() },
            UIAction(title: "Previous video", image: UIImage(systemName: "backward.end.fill"),
                     attributes: model.queue.hasPrevious ? [] : .disabled) { _ in model.previous() },
            UIAction(title: "Next video", image: UIImage(systemName: "forward.end.fill")) { _ in model.next() }
        ]
        let queue = UIHostingController(rootView: UpNextView(model: model))
        queue.title = "Up Next"
        queue.preferredContentSize = CGSize(width: 1400, height: 480)
        controller.customInfoViewControllers = [queue]
    }
    static func dismantleUIViewController(_ controller: AVPlayerViewController, coordinator: Coordinator) {
        for gesture in coordinator.playlistGestures { controller.view.removeGestureRecognizer(gesture) }
        controller.delegate = nil
        coordinator.controller = nil
    }
    final class Coordinator: NSObject, UIGestureRecognizerDelegate, AVPlayerViewControllerDelegate {
        var model: PlayerModel
        let session: PlaybackSession
        weak var controller: AVPlayerViewController?
        private var transportBarVisible = false
        private var pictureInPictureStarting = false
        private var wasFullScreen = false
        func updateFocus(fullScreen: Bool) {
            defer { wasFullScreen = fullScreen }
            guard fullScreen && !wasFullScreen else { return }
            // An overlay has no presentation transition to transfer focus from
            // the disabled library. Ask its containing focus environment instead.
            DispatchQueue.main.async { [weak self] in
                guard let self, self.session.model === self.model, self.session.isFullScreen,
                      let root = self.controller?.view.window?.rootViewController else { return }
                root.setNeedsFocusUpdate()
                root.updateFocusIfNeeded()
            }
        }
        lazy var nextGesture = makeSwipe(direction: .right)
        lazy var previousGesture = makeSwipe(direction: .left)
        var playlistGestures: [PlaylistSwipeGestureRecognizer] { [nextGesture, previousGesture] }
        private func makeSwipe(direction: UISwipeGestureRecognizer.Direction) -> PlaylistSwipeGestureRecognizer {
            let gesture = PlaylistSwipeGestureRecognizer(target: self, action: #selector(changeVideo(_:)))
            gesture.name = direction == .right ? "Swipe right for next video" : "Swipe left for previous video"
            gesture.direction = direction
            gesture.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.indirect.rawValue)]
            gesture.allowedPressTypes = []
            gesture.cancelsTouchesInView = false
            gesture.delegate = self
            return gesture
        }
        init(model: PlayerModel, session: PlaybackSession) { self.model = model; self.session = session }
        private var canChangeVideo: Bool {
            session.model === model && session.isFullScreen && !pictureInPictureStarting &&
                !model.preparing && model.error == nil && !model.finished
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
            // Decide at finger-down, not completion. Paused scrubbing, menus,
            // the mini player and Up Next keep their normal touch behavior.
            guard let swipe = gestureRecognizer as? PlaylistSwipeGestureRecognizer,
                  touch.type == .indirect, canChangeVideo, !transportBarVisible, model.player.rate > 0,
                  let item = model.player.currentItem,
                  controller?.presentedViewController == nil else { return false }
            if let controller, let focusedView = UIFocusSystem.focusSystem(for: controller)?.focusedItem as? UIView,
               controller.customInfoViewControllers.contains(where: { info in
                   info.viewIfLoaded.map { focusedView.isDescendant(of: $0) } ?? false
               }) { return false }
            swipe.startingItem = item
            swipe.startingIndex = model.queue.index
            return true
        }
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
            // AVKit's touch/pan recognizers may reveal controls during a swipe.
            // They must not cancel a playlist swipe that started with controls hidden.
            gestureRecognizer is PlaylistSwipeGestureRecognizer
        }
        func playerViewController(_ playerViewController: AVPlayerViewController, willTransitionToVisibilityOfTransportBar visible: Bool, with coordinator: AVPlayerViewControllerAnimationCoordinator) {
            transportBarVisible = visible
        }
        func playerViewControllerShouldDismiss(_ playerViewController: AVPlayerViewController) -> Bool {
            // AVKit cannot dismiss an embedded controller itself. Menu still
            // ends full-screen playback through the owning library session.
            if session.model === model && session.isFullScreen && !pictureInPictureStarting { session.stop() }
            return false
        }
        func playerViewControllerWillStartPictureInPicture(_ playerViewController: AVPlayerViewController) {
            pictureInPictureStarting = true
        }
        func playerViewControllerShouldAutomaticallyDismissAtPictureInPictureStart(_ playerViewController: AVPlayerViewController) -> Bool { false }
        func playerViewControllerDidStartPictureInPicture(_ playerViewController: AVPlayerViewController) {
            pictureInPictureStarting = false
            guard session.model === model else { return }
            session.didStartPictureInPicture()
        }
        func playerViewControllerDidStopPictureInPicture(_ playerViewController: AVPlayerViewController) {
            guard session.model === model else { return }
            session.didStopPictureInPicture()
        }
        func playerViewController(_ playerViewController: AVPlayerViewController, failedToStartPictureInPictureWithError error: Error) {
            pictureInPictureStarting = false
            guard session.model === model else { return }
            session.pictureInPictureError = "Your video is still playing. Try again, or use Browse in mini player to keep watching inside mvideo."
        }
        func playerViewController(_ playerViewController: AVPlayerViewController, restoreUserInterfaceForPictureInPictureStopWithCompletionHandler completionHandler: @escaping (Bool) -> Void) {
            guard session.model === model else { completionHandler(false); return }
            session.restore()
            // Let SwiftUI restore the retained controller's full-screen bounds first.
            DispatchQueue.main.async { [weak self] in
                guard let self, self.session.model === self.model else { completionHandler(false); return }
                playerViewController.view.superview?.layoutIfNeeded()
                completionHandler(true)
            }
        }
        @objc func changeVideo(_ gesture: PlaylistSwipeGestureRecognizer) {
            guard gesture.state == .ended, canChangeVideo,
                  let item = gesture.startingItem, item === model.player.currentItem,
                  gesture.startingIndex == model.queue.index else { return }
            // Consume once, and ignore a swipe spanning automatic-next or a new selection.
            gesture.startingItem = nil
            gesture.startingIndex = nil
            if gesture.direction == .right { model.next() }
            else if gesture.direction == .left { model.previous() }
        }
    }
}
struct UpNextView: View {
    @Bindable var model: PlayerModel
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("\(model.queue.index + 1) of \(model.queue.ids.count) · \(model.title)").font(.title3.bold())
            Text(model.normalizationEnabled ? model.normalizationMessage : "Volume normalization off")
                .font(.caption).foregroundStyle(Theme.secondary)
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
