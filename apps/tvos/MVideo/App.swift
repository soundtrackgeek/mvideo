import SwiftUI

@MainActor @Observable final class AppSession {
    var api: API?
    var connectionError: String?
    init() {
        if let connection = KeychainStore().load() { api = API(connection) }
    }
    func pair(origin: String, code: String) async throws {
        let url = try Connection.origin(origin)
        let candidate = API(Connection(origin: url, token: ""))
        struct Pair: Decodable { let token: String }
        let result: Pair = try await candidate.request("/api/pair", method: "POST", body: JSONEncoder().encode(["code": code]))
        let connection = Connection(origin: url, token: result.token)
        try KeychainStore().save(connection)
        api = API(connection)
    }
    func disconnect() async {
        if let api {
            struct Revoked: Decodable { let ok: Bool }
            do { let _: Revoked = try await api.request("/api/session", method: "DELETE") }
            catch { connectionError = "Local session removed. Server revocation was unavailable; revoke it on the PC if needed." }
        }
        KeychainStore().clear(); api = nil
    }
}
@main struct MVideoApp: App {
    @State private var session = AppSession()
    var body: some Scene {
        WindowGroup {
            Group {
                if let api = session.api { LibraryShell(api: api, session: session) }
                else { PairingView(session: session) }
            }
            .preferredColorScheme(.dark)
            .tint(Theme.amber)
            .task {
                #if DEBUG && targetEnvironment(simulator)
                let environment = ProcessInfo.processInfo.environment
                if let origin = environment["MVIDEO_TEST_ORIGIN"], let code = environment["MVIDEO_TEST_PAIR_CODE"] {
                    do { try await session.pair(origin: origin, code: code) }
                    catch { session.connectionError = error.localizedDescription }
                }
                #endif
            }
        }
    }
}
struct PairingView: View {
    @Bindable var session: AppSession
    @State private var origin = ""
    @State private var code = ""
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            HStack(spacing: 100) {
                VStack(alignment: .leading, spacing: 24) {
                    Text("mvideo").font(.system(size: 38, weight: .bold))
                    Text("Your own music\ntelevision.").font(.system(size: 76, weight: .bold))
                    Text("Connect your library.\nRediscover every era.").font(.system(size: 30)).foregroundStyle(Theme.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 28) {
                    Text("Connect your Apple TV").font(.title2.bold())
                    Text("Use your mvideo server’s HTTPS address and the pairing code shown on your PC.").foregroundStyle(Theme.secondary)
                    TextField("https://your-server:port", text: $origin).textContentType(.URL).autocorrectionDisabled().textInputAutocapitalization(.never).accessibilityIdentifier("server-origin")
                    SecureField("Eight-digit pairing code", text: $code).keyboardType(.numberPad).accessibilityIdentifier("pair-code")
                    Button(busy ? "Connecting…" : "Connect library") {
                        busy = true; error = nil
                        Task {
                            do { try await session.pair(origin: origin, code: code); code = "" }
                            catch { self.error = error.localizedDescription }
                            busy = false
                        }
                    }.disabled(busy || origin.isEmpty || code.count != 8).buttonStyle(PillStyle()).accessibilityIdentifier("connect")
                    if let error = error ?? session.connectionError { Text(error).foregroundStyle(Theme.amber).font(.callout) }
                }.frame(width: 620)
            }.padding(90)
        }.foregroundStyle(Theme.ivory)
    }
}
