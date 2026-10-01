import SwiftUI

struct FacetCard: View {
    let api: API
    let facet: Facet
    let title: String

    var body: some View {
        Color.clear.frame(height: 270)
            .overlay {
                Artwork(url: (facet.image ?? facet.thumbnail).flatMap { try? api.connection.url($0) },
                        fallbackURL: facet.thumbnail.flatMap { try? api.connection.url($0) })
            }
            .overlay {
                LinearGradient(stops: [
                    .init(color: .black.opacity(0.1), location: 0),
                    .init(color: .black.opacity(0.45), location: 0.35),
                    .init(color: .black.opacity(0.92), location: 1)
                ], startPoint: .top, endPoint: .bottom)
            }
            .overlay(alignment: .bottomLeading) {
                VStack(alignment: .leading, spacing: 10) {
                    Text(title).font(.system(size: 36, weight: .bold)).lineLimit(2)
                    HStack(alignment: .firstTextBaseline) {
                        Text("\(facet.count.formatted()) \(facet.count == 1 ? "video" : "videos")")
                        Spacer(minLength: 12)
                        if let attribution = facet.imageAttribution {
                            Text(attribution).font(.system(size: 18))
                        }
                    }.font(.system(size: 23)).foregroundStyle(.white.opacity(0.9))
                }
                .foregroundStyle(.white).shadow(color: .black.opacity(0.8), radius: 3, y: 1)
                .padding(26)
            }
            .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
