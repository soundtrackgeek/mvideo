import SwiftUI

enum Theme {
    static let background = Color(red: 0.035, green: 0.043, blue: 0.047)
    static let ivory = Color(red: 0.96, green: 0.945, blue: 0.91)
    static let amber = Color(red: 0.98, green: 0.73, blue: 0.38)
    static let secondary = Color(red: 0.67, green: 0.68, blue: 0.67)
}
struct PillStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { PillBody(configuration: configuration) }
    private struct PillBody: View {
        let configuration: Configuration
        @Environment(\.isFocused) private var focused
        var body: some View {
            configuration.label.font(.system(size: 25, weight: .semibold))
                .padding(.horizontal, 28).padding(.vertical, 18)
                .foregroundStyle(focused ? Theme.background : Theme.ivory)
                .background(focused ? Theme.ivory : Color.white.opacity(0.075), in: Capsule())
                .overlay(Capsule().strokeBorder(focused ? Theme.ivory : Color.white.opacity(0.15), lineWidth: focused ? 3 : 1))
                .scaleEffect(configuration.isPressed ? 0.98 : focused ? 1.035 : 1)
                .shadow(color: focused ? Theme.ivory.opacity(0.18) : .clear, radius: 18)
                .animation(.easeOut(duration: 0.15), value: focused)
        }
    }
}
struct CardStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { CardBody(configuration: configuration) }
    private struct CardBody: View {
        let configuration: Configuration
        @Environment(\.isFocused) private var focused
        var body: some View {
            configuration.label
                .padding(9)
                .background(focused ? Color.white.opacity(0.09) : .clear, in: RoundedRectangle(cornerRadius: 15))
                .overlay(RoundedRectangle(cornerRadius: 15).strokeBorder(focused ? Theme.ivory : .clear, lineWidth: 3))
                .scaleEffect(focused ? 1.035 : 1)
                .animation(.easeOut(duration: 0.15), value: focused)
        }
    }
}
struct Artwork: View {
    let url: URL?
    var fallbackURL: URL? = nil
    var body: some View {
        AsyncImage(url: url) { phase in
            if phase.error != nil, let fallbackURL {
                AsyncImage(url: fallbackURL) { fallback in content(fallback) }
            } else { content(phase) }
        }.clipped().accessibilityHidden(true)
    }
    @ViewBuilder private func content(_ phase: AsyncImagePhase) -> some View {
            if let image = phase.image { image.resizable().scaledToFill() }
            else {
                ZStack {
                    LinearGradient(colors: [Color(red: 0.18, green: 0.19, blue: 0.19), Theme.background], startPoint: .topLeading, endPoint: .bottomTrailing)
                    Image(systemName: "music.note.tv").font(.system(size: 54, weight: .ultraLight)).foregroundStyle(Theme.secondary.opacity(0.55))
                }
            }
    }
}
