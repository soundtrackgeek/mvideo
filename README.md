# mvideo

A native Apple TV music video app backed by an independent Windows library and streaming service. The five [approved designs](docs/design/README.md) guide the charcoal, warm-white and amber interface. The collection spans every era present in the files.

The Windows service and native tvOS app are implemented. The app supports artist/title/year search, artist biographies and fanart.tv photography, year/decade browsing, full-selection shuffle, continuous playback, queue controls and return to the previous focused video and scroll position. Home chooses a random fanart.tv background from verified artists in the library at launch, keeps it stable while browsing, and falls back to a video thumbnail.

Artist tiles use cached, verified fanart.tv photography when available, otherwise a still from that artist's videos. Year and decade tiles use a still from a video dated within that period. Dark gradients keep names and counts readable. On artist pages, move down past the videos to focus **Artist photos**, then select a photo to view it full-screen; use Previous/Next or Menu to return. Player controls display **Artist - Track (Year)**, omitting missing metadata.

The real Windows catalog contains **15,559 videos**. Version **0.3.0 (1)** is available to the invited tester in its dedicated TestFlight group. The requested invitation was sent to `jtillnes2@yahoo.com`. See [verification evidence](docs/implementation/VERIFICATION.md) for current TestFlight and device status.

## Library service

Python 3.12+, FFmpeg/FFprobe on PATH. SQLite FTS5 indexes artist, song and year with paginated results. Scans compare size/mtime, retain ambiguous filenames for review and never write into the media root. Offline or incomplete directory walks retain the catalog. Metadata, thumbnails and converted playback copies live in a separate state directory.

```sh
python3 -m venv .venv
.venv/bin/pip install -e './server[test]'
export MVIDEO_LIBRARY='/path/to/read-only/media'
export MVIDEO_STATE='/path/to/mvideo-state'
.venv/bin/mvideo --env .env scan
.venv/bin/mvideo --env .env serve
# In another terminal, using the same MVIDEO_STATE:
.venv/bin/mvideo pair
.venv/bin/pytest server/tests -q
```

The service binds `127.0.0.1:8765`. The installed private HTTPS origin is **`https://jorncomputer.tail5ef358.ts.net:8443`**, verified against the Windows service. Tailscale Serve forwards that port to mvideo. Tonehavn's existing port 443 route remains separate. The Apple TV must be on the same tailnet; no public endpoint or Funnel is enabled.

### Windows installation and startup

Installed source: `L:\mvideo-service`. Read-only media: `L:\MusicVideos`. Python 3.13 and FFmpeg are installed on this PC. For another installation, install Python 3.12+ and FFmpeg/FFprobe first, then run from the repository:

```powershell
.\scripts\windows-diagnostics.ps1
.\scripts\windows-save-providers.ps1
.\scripts\windows-start.ps1 -Scan
# From an administrator PowerShell, once:
.\scripts\windows-install-boot-task.ps1
# Configure a separate private HTTPS route after inspecting existing routes:
.\scripts\windows-publish.ps1
# Generate the code shown on the Apple TV pairing screen:
.\scripts\windows-start.ps1 -Pair
```

The installed **mvideo Library** Task Scheduler task starts 30 seconds after Windows boots, runs as **Local Service**, requires no interactive login, and restarts after failures. It scans at startup and every 30 minutes. Tailscale's own Windows service is set to Automatic. No terminal must remain open. The PC must remain powered on and awake for streaming; reboot startup configuration and a fresh task launch have been verified, but an actual PC reboot has not been performed.

Runtime state is **`C:\ProgramData\mvideo`**: catalog, metadata, thumbnails, conversions and `service.log`. The installer migrates the earlier per-user database, protects service code against changes by the service account, and restricts state access to Local Service, the installer account, Administrators and SYSTEM. Provider keys are encrypted with machine DPAPI inside that restricted directory. Library files and their permissions remain unchanged. The initial interactive setup stores keys in current-user DPAPI; rerun the boot installer after changing those keys to update the background copy. `LAST_FM_SECRET` is unnecessary for the public biography API.

For maintenance, use Task Scheduler's **mvideo Library** task, or run `Stop-ScheduledTask` / `Start-ScheduledTask -TaskName 'mvideo Library'` in an administrator PowerShell. `windows-install-task.ps1` remains an optional sign-in-only launcher for development; production uses `windows-install-boot-task.ps1`. `windows-start.ps1` without flags is a foreground development server; do not start it while the background task owns port 8765.

`windows-provision.ps1` supports an encrypted one-time transfer from another computer when interactive key entry is inconvenient. Provider credentials never enter the tvOS app, Git or request logs. `windows-verify.ps1` writes local diagnostic reports and a five-minute pairing-code handoff; consume the code immediately and remove its file.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `MVIDEO_LIBRARY` | `L:\MusicVideos` | Read-only source directory |
| `MVIDEO_STATE` | `.state` (installed Windows task uses ProgramData) | Database and derived caches; must be outside source root |
| `MVIDEO_FFMPEG`, `MVIDEO_FFPROBE` | executable names on PATH | Installed tools |
| `MVIDEO_CACHE_GB` | `20` | Playback conversion cache budget |
| `LAST_FM` | unset | Server-only Last.fm API key |
| `FANART_TV` | unset | Server-only fanart.tv project API key |

Pairing codes last five minutes and lock after five unsuccessful attempts. Successful pairing consumes the code and issues a 90-day session. Server stores only session hashes; clients save tokens in their own Keychain namespace. `mvideo revoke-all` revokes every mvideo session, including its media tickets. Access logs are disabled because media paths contain scoped expiring tickets. Configure any reverse proxy to avoid logging these paths or Authorization headers too.

### Artist identity and filename review

A filename such as `a-ha - Take On Me (1985)` yields artist/title/year. Multiple spaced separators, missing years and multiple parenthesized years are flagged rather than silently guessed. Unidentified videos remain searchable and playable. Use an application-state override, then rescan:

```sh
mvideo override VIDEO_ID --artist 'Artist' --title 'Song' --year 1985
mvideo scan
mvideo identity 'a-ha' 7364dea6-ca9a-48e3-be01-b44ad0d19897
```

Artist identities are explicitly verified; the first installed artwork pool includes a-ha, Duran Duran and Tears for Fears. Additional artists become eligible for home photography after their identity is approved and artwork loaded. Name capitalization variants share an artist scope.

Only approve an artist MusicBrainz UUID after checking the artist's identity. Name-only Last.fm results are candidates; the app must show metadata unavailable until identity is verified. Verified metadata is cached for 24 hours; failed/missing matches for 15 minutes. Requests are serialized at no more than one per second with rate-limit backoff. Artist pages carry Last.fm and fanart.tv credit/source links. No provider crawl is performed during scanning.

### Playback and queues

The server uses actual FFprobe stream metadata, not extensions. Conservative first-generation Apple TV 4K baseline: progressive H.264 up to 1080p/60, 8-bit 4:2:0 and AAC-LC stereo in MP4 plays directly. Compatible streams in other containers are remuxed; incompatible audio/video receives a cached H.264/AAC MP4 derivative. Interlaced material is deinterlaced; sample aspect ratio is preserved. HDR needs explicit compatibility review and is not silently converted to washed-out SDR.

Conversions run one at a time and must finish before playback, enabling full-file byte-range seeking. Initial conversion can take time, especially 4K VP9. Original files remain unchanged. Native playback prefetches the next queue item. HLS/adaptive renditions are evaluated in the plan but are not currently implemented. Cache outputs are pinned while media tickets remain valid; old unpinned outputs are evicted. A full cache reports a recoverable conversion error.

A queue snapshots all matching IDs, not just the visible page. Shuffle is a permutation without repeats. Selecting a video starts there and wraps through the rest of the same scope once. At exhaustion the app can offer replay. Deleted/unavailable items produce explicit retry/skip behavior.

## Apple TV and TestFlight

The dedicated app is **mvideo - music videos**, bundle `com.soundtrackgeek.mvideo`, Apple team `3L5769JKCM`, minimum tvOS 18. Its session lives in Keychain service `com.soundtrackgeek.mvideo`; provider keys never reach the app. The shorter App Store name was already taken. [App Store Connect](https://appstoreconnect.apple.com/apps/6818073365/testflight/tvos).

Install mvideo through its TestFlight invitation, open Tailscale on Apple TV and connect to your tailnet, then enter the HTTPS origin above and a fresh eight-digit code from the Windows pairing command. Use Connection in the navigation bar to disconnect or pair again. The owner has installed, paired and played videos on the physical Apple TV. It is believed to be a first-generation Apple TV 4K; the exact model and tvOS version remain unverified.

Open `apps/tvos/MVideo.xcodeproj` in Xcode. `apps/tvos/project.yml` regenerates the project with XcodeGen. Tests include an optional live-library suite: pair the simulator first, then run the MVideo scheme tests; otherwise live tests explicitly skip. Use normal simulator signing so Keychain works.

Distribution was verified with Xcode 26.6. With the team's existing Xcode account, archive and export:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -project apps/tvos/MVideo.xcodeproj -scheme MVideo -configuration Release \
  -destination 'generic/platform=tvOS' -archivePath output/MVideo.xcarchive \
  CODE_SIGNING_ALLOWED=NO archive
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
  -exportArchive -archivePath output/MVideo.xcarchive \
  -exportOptionsPlist apps/tvos/ExportOptions.plist -exportPath output/export \
  -allowProvisioningUpdates
```

The export applies App Store distribution signing to the archive. For upload, use an export-options copy with `destination` set to `upload`, or Xcode Organizer. Increment the build number for each upload. Upload success, Apple processing and tester availability are separate checks.

## Design and evidence

- [Implementation plan](docs/implementation/PLAN.md)
- [Verification and delivery gates](docs/implementation/VERIFICATION.md)
- [Approved images](docs/design/README.md) and [generation prompts](docs/design/PROMPTS.md)

Generated concept photography, counts and example biographies are reference material only and are never treated as real catalog/provider data.
