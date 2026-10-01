import SwiftUI

struct ArtistPhotoSelection: Identifiable { let id: Int }

struct ArtistPhotoViewer: View {
    let api: API
    let artist: String
    let metadata: ArtistMetadata
    @Environment(\.dismiss) private var dismiss
    @State private var index: Int

    init(api: API, artist: String, metadata: ArtistMetadata, initialIndex: Int) {
        self.api = api; self.artist = artist; self.metadata = metadata
        _index = State(initialValue: initialIndex)
    }

    var body: some View {
        VStack(spacing: 24) {
            HStack {
                Text(artist).font(.title2.bold())
                Spacer()
                Text("\(index + 1) / \(metadata.images.count)").foregroundStyle(Theme.secondary)
                    .accessibilityIdentifier("photo-position")
            }
            GeometryReader { geometry in
                AsyncImage(url: try? api.connection.url(metadata.images[index])) { phase in
                    if let image = phase.image { image.resizable().scaledToFit() }
                    else if phase.error != nil { Text("This photo is unavailable. Try another photo.").foregroundStyle(Theme.secondary) }
                    else { ProgressView("Loading photo…") }
                }.frame(width: geometry.size.width, height: geometry.size.height)
            }
            HStack(spacing: 32) {
                Text(metadata.imageAttribution ?? "Artist images · fanart.tv").font(.system(size: 21)).foregroundStyle(Theme.secondary)
                Spacer()
                Button("Previous") { index -= 1 }.disabled(index == 0).accessibilityIdentifier("photo-previous")
                Button("Next") { index += 1 }.disabled(index == metadata.images.count - 1).accessibilityIdentifier("photo-next")
                Button("Close") { dismiss() }.accessibilityIdentifier("photo-close")
            }.buttonStyle(PillStyle())
        }
        .padding(60).background(Theme.background).foregroundStyle(Theme.ivory)
        .onExitCommand { dismiss() }
    }
}
