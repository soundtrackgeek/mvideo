# Implementation and delivery plan

Approved designs: `cbc4a5a`, all five images inspected 2026-10-01. Design approval is recorded in the owner's implementation request. Every displayed item/count must come from the service. Generated reference artwork is never shipped as library content.

## Verified starting conditions (2026-10-01)

- Repository has no application/service code; clean `master` at `cbc4a5a`.
- Tailscale is running. `jorncomputer.tail5ef358.ts.net` resolves to `100.105.78.85`; peer is Windows, online, ping 4 ms over LAN.
- TCP 22, 443, 445 and 5985 respond. HTTPS `/` redirects to `/app/`; this is an existing service, not an mvideo endpoint. Do not replace its route or infer its media API.
- SSH as the Mac username `jtillnes` rejects noninteractive authentication. Windows drive contents, service configuration, FFmpeg installation and actual codec distribution are still unverified. Owner asked for existing access.
- Local `.env` contains the three named provider variables (values never printed).
- Tonehavn inspected read-only: native SwiftUI iOS client, automatic signing, team `3L5769JKCM`, `com.soundtrackgeek.tonehavn`, shared scheme, Xcode Cloud target manifest, export-compliance declaration. No reusable local upload script or App Store Connect API key found in its repository or standard key directories. Its identity/configuration remain untouched.
- Xcode 27 and Xcode 26.x installations; tvOS 26.5/27 simulators available. Valid Apple Development and Apple Distribution identities for the owner/team are installed. No physical Apple TV paired. Target model/version requested from owner.

## Milestone 1 — Windows library service (0.2.0)

Python 3.12+, FastAPI/Uvicorn, SQLite WAL + FTS5. Keep DB, thumbnails, metadata and playback caches outside the source root. Read media only. Configure the library explicitly; Windows default `L:\MusicVideos`. Bind loopback by default. Supply PowerShell setup/start/diagnostic commands; establish a separate HTTPS route only after inspecting the Windows Tailscale Serve configuration. Never reset Serve or enable Funnel.

Incremental scan compares path/size/mtime, probes changed files with ffprobe, records failures, detects disappeared files only after a complete successful walk. Offline/inaccessible roots must not erase the library. Conservative filename parsing preserves raw names and ambiguity; explicit sidecar overrides live in application state, never source media. Indexed artist/title/year prefix-token search; capped pagination, stable sort and catalog revision. Artist/year/decade facets include all eras and an unknown-year path. Thumbnail work lazy and cached.

Authentication: owner creates a short-lived one-time pairing code locally; bounded attempts; random session tokens stored hashed server-side. API bearer authentication, scoped expiring media tickets, session revocation. Production client accepts HTTPS origins; localhost HTTP allowed only for Debug simulator verification. Apple saved sessions use Keychain service `com.soundtrackgeek.mvideo`, with no Tonehavn access groups or plain-file secrets. Disable credential-bearing request/access logs.

Metadata: server-only Last.fm biography requests (API key; shared secret not required by artist.getInfo), fanart.tv images keyed by MusicBrainz artist UUID. Resolve identity conservatively; exact-name matches are candidates, not proof for homonyms. Provide explicit MBID mapping/approval for ambiguous or unverified artists. Lazy metadata, positive/negative caches, bounded provider concurrency/rate, backoff on 429/provider errors, source URLs and attribution. No 15,000-item provider crawl.

Playback: probe streams, profile/level, pixel format, dimensions, frame rate, field order, audio and container. Conservative H.264/AAC MP4 direct baseline; compatible video in another container remux; incompatible video/audio transcode to bounded SDR H.264/AAC. Unknown/HDR cases explicit until validated. Preserve aspect ratio, deinterlace when necessary; never modify input. Evaluate HLS against completed MP4 VOD: first delivery uses byte-range MP4 and completed cached conversions for dependable full-range seeking; preparation status and next-item prefetch hide work where possible. HLS/adaptive rendition support is a later bandwidth optimization, not an assumed current endpoint. Bound conversion concurrency, timeout and cache size.

Verification: parser ambiguity/punctuation/Unicode/year cases; unchanged/changed/deleted/offline scans; FTS and scope intersections; 15k pagination; queue permutation/selected-start/no repeat; authorization, traversal, byte ranges; codec policy and FFmpeg-generated fixtures. Actual Windows media evidence remains separately required.

## Milestone 2 — Native tvOS app (0.3.0)

Dedicated `com.soundtrackgeek.mvideo` identity, team `3L5769JKCM`, tvOS 18+, shared Xcode scheme and reproducible project. Native SwiftUI charcoal/ivory/amber shell with Home/Search/Artists/Years/Decades. Photo-led heroes from real server artwork/thumbnails, native text input, paginated grids and focus sections. Server pairing/settings, loading/empty/offline/artwork fallbacks and retry actions.

AVPlayer/AVKit full-screen playback: scope snapshot queue, selected-video start, full-scope shuffle, no repeats within a cycle, previous/next/retry/skip and up-next display. Native transport handles pause/seek/audio/aspect-fit. Keep the browsing view and its page/focus/scroll identity alive under player presentation. Cancel stale search and playback work. Never bundle provider credentials or mock library records.

Verification: compile and run on tvOS simulator; deterministic native request/origin/queue tests; remote navigation, keyboard, browse scopes, dismissal/restoration and error recovery. Local fixture service can prove integration, but label generated fixture media explicitly and keep it out of production.

## Milestone 3 — Integration and TestFlight (0.4.0 when verified)

Inspect Windows services/Serve, install isolated service, securely provision server credentials, scan real library, summarize actual codecs and sample each format without altering originals. Validate direct/remux/transcode audio, aspect ratio, seeking and transitions. Run physical-device protocol when Apple TV is available.

Create mvideo's own app assets, bundle/provisioning and App Store Connect app. Follow automatic signing and shared-scheme approach from Tonehavn. Use stable supported Xcode for distribution; archive, export/validate and upload with available account credentials. If API access or app creation requires owner action, record the exact failed step and required action. Report archive, upload, processing and TestFlight group availability separately; do not claim TestFlight availability from upload alone. Xcode Cloud IDs must be mvideo-generated, never copied from Tonehavn.

## Delivery discipline

For each coherent implementation milestone: meaningful tests, README/configuration updates, dated semantic CHANGELOG, descriptive commit, `git push`. Evidence and unresolved gates live in `docs/implementation/VERIFICATION.md`. Continue independent work while access questions are pending. Do not invent passing device/provider/library/release results.
