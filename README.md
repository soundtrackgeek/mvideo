# mvideo

A native Apple TV music video app backed by an independent Windows library and streaming service. The five [approved designs](docs/design/README.md) guide the charcoal, warm-white and amber interface. The collection spans every era present in the files.

The Windows service and native tvOS app are implemented. The app supports shared playlists with a browser editor, artist/title/year search, artist biographies and fanart.tv photography, year/decade browsing, full-selection shuffle, continuous playback, queue controls and return to the previous focused video and scroll position. Home chooses a random fanart.tv background from verified artists in the library at launch, keeps it stable while browsing, and falls back to a video thumbnail.

Artist tiles and pages automatically look up fanart.tv photography as you browse. The server matches artists against MusicBrainz recording credits using songs in your library, then caches their photos. Tiles replace temporary video stills when photos arrive; unmatched artists or missing provider photos keep the fallback. Year and decade tiles use a still from a video dated within that period. Dark gradients keep names and counts readable. On artist pages, move down past the videos to focus **Artist photos**, then select a photo to view it full-screen; use Previous/Next or Menu to return. Player controls display **Artist - Track (Year)**, omitting missing metadata.

The current Windows catalog contains **15,558 videos** after moving one unknown-year video aside. The owner's completed loudness scan reports **15,541 measured videos and 17 errors**. Apple TV updates are delivered through the dedicated **mvideo testers** TestFlight group. The requested invitation to `jtillnes2@yahoo.com` was accepted; update mvideo through TestFlight on Apple TV. See [verification evidence](docs/implementation/VERIFICATION.md) for current TestFlight and device status.

## Playlists and browser editor

Open **[Playlist studio](https://jorncomputer.tail5ef358.ts.net:8443/studio/)** from a computer or phone on your tailnet. The editor is served by mvideo itself; no separate account, web host or public endpoint is needed. Pair the browser with a fresh eight-digit code from `scripts/windows-start.ps1 -Pair` on the PC. The browser keeps its session in this tab’s session storage; Disconnect revokes it.

The server now contains **Eurodance (37 videos)**, **Glam metal & hard rock (42)** and **Chart toppers (24)**. These are handpicked songs from your catalog, with artists interleaved. Chart toppers uses verified UK Top 10 singles. See the [complete track lists and chart sources](docs/playlists.md).

- Create a playlist, search by artist/title/year, and narrow results by decade. Search results are paginated across the full catalog.
- Drag a video into the playlist, or use **Add**. Drag rows to change their order; the up/down buttons also work with keyboard and touch. Duplicate video IDs are prevented.
- Rename, edit the description, remove videos and choose **Save changes**. Unsaved work is protected when switching playlists or closing the tab. If another editor saved first, your draft stays visible and the server refuses to overwrite it; **Reload saved playlist** retrieves the current version after confirming that you want to discard your draft.
- On Apple TV, open **Playlists**, choose a mix and use **Play all**, **Shuffle selection**, or select a video. Saved order is preserved, and playback includes the whole playlist. Use **Refresh playlists** / **Refresh playlist** after editing; returning from the background refreshes these screens too.
- Playlists belong to the shared server library, so every paired device can read and edit them. Up to 5,000 distinct videos per playlist are supported. Unavailable videos remain visible in the editor and are skipped by playback; deleting a playlist leaves the media files intact.

Starter recipes can be previewed and installed on another indexed server:

```sh
mvideo seed-playlists          # preview matching/missing songs
mvideo seed-playlists --apply  # create each starter once, preserving later edits/deletions
```

Playlist records and ordered video references are stored in the existing SQLite database. Back up the state directory using SQLite’s backup API (or with the service stopped). The schema is added automatically on startup.

The React/Vite source is in `apps/web`; the compiled editor is included in the Python package, so Windows does not need Node.js at runtime. After editing the web source, rebuild and commit the generated assets:

```sh
npm ci --prefix apps/web
npm run build --prefix apps/web
npm test --prefix apps/web
# Optional development server; mvideo API must run on localhost:8765:
npm run dev --prefix apps/web
```

Authenticated API: `GET/POST /api/playlists`, `GET/PUT/DELETE /api/playlists/{id}`. Writes use `{name, description, ids}`; updates additionally require the last read `version`, and deletion requires `?version=N`. Conflicts return 409. `/api/videos?playlist=ID` and `/api/queue` with `{playlist: ID, shuffle: true}` support the same search filters as the library. There is no cross-origin API access; host the editor on the server origin.

## Library service

Python 3.12+, FFmpeg/FFprobe on PATH. SQLite FTS5 indexes artist, song and year with paginated results. Scans compare size/mtime, retain ambiguous filenames for review and never write into the media root. Offline or incomplete directory walks retain the catalog. Metadata, thumbnails and converted playback copies live in a separate state directory.

The explicit `fix-filenames --apply` maintenance command is an exception: it renames the files listed in a reviewed plan and can move listed unknown-year videos to a sibling review folder. Ordinary scanning, playback and loudness analysis remain read-only with respect to source media.

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

Artist matching is automatic when exact artist (or alias) and song-title credits identify one MusicBrainz artist. It checks up to three library songs, uses two matching songs when available, and accepts an unambiguous single-song match for small libraries. Conflicting identities, collaboration credits and truncated search results remain unresolved. Explicit `mvideo identity` mappings override automatic matches. Cached matched artists also join the home-background pool. Name capitalization variants share an artist scope.

Only set a manual MusicBrainz UUID after checking the artist's identity. Name-only Last.fm results remain candidates; they do not unlock photos by themselves. Metadata and missing matches are cached for 24 hours; transient failures retry after 15 minutes. Visible artist tiles and opened pages trigger a single background worker with a maximum of 64 pending artists, while the app refreshes results without blocking navigation. Requests are serialized at no more than one per second with rate-limit backoff and an identifying User-Agent. Artist pages carry Last.fm and fanart.tv credit/source links. No provider crawl is performed during scanning.

#### Repair inconsistent filenames

The **0.8.0 source** includes the [complete 15,559-file audit and reviewed repair list](docs/filename-repairs.md): **183 renames**, using the six years supplied by the owner, and **one move aside** for Matt Cox — Washed It All Away, whose year is unknown. The target format is `Artist - Title (Year).ext`. Existing clear years are retained; future unknown/ambiguous years are reported for manual decisions.

Stop the loudness scan with Ctrl+C and close active playback/playlist editing before applying. Run from the updated checkout on the Windows PC:

```powershell
git pull --ff-only
.\scripts\windows-fix-filenames.ps1          # preview; expect 184 ready actions for the audited library
.\scripts\windows-fix-filenames.ps1 -Apply   # perform the listed moves and migrate the catalog
```

The launcher uses the same installed-service configuration/Python fallback as the loudness launcher; `-Library`, `-State`, `-PythonPath` and an optional `-Plan` JSON path are supported. Portable equivalents are `mvideo fix-filenames` and `mvideo fix-filenames --apply`. Each apply creates a SQLite backup under the state directory's `backups` folder, rejects destination conflicts and changed sources, and locks against concurrent catalog/loudness scans. Playlist references/order, metadata overrides and saved measurements migrate with the new filename-derived IDs. A durable journal supports resuming interrupted moves by rerunning `-Apply`.

Matt Cox's file moves to `L:\MusicVideos - Needs Review` beside the current library and remains recorded as unavailable, preserving its references for later restoration. Media contents and modification times are retained. Refresh the Apple TV library after completion, then resume loudness analysis; thumbnails/conversions may regenerate under the new IDs. These source commands run against the existing service database without redeploying the service or Apple TV app. See the audit for every proposed name, the complete year-decision list, and recovery details.

### Playback and queues

#### Normalize volume on Apple TV

Version **0.9.0** uses the saved measurements to adjust each video's audio **on the Apple TV during playback**. **Normalize volume** is on by default and appears beside Previous/Next in the player controls. The setting persists across videos and app launches; switching it smoothly changes the current video's gain. Up Next shows whether normalization is active or the video is playing at its original volume.

The target is **-18 LUFS**. Gain is capped to keep the source's measured true peak at or below **-2 dBTP**, with a maximum **+12 dB** boost. Some quiet or highly dynamic tracks therefore remain below the target. The adjustment is constant within each song, preserving its dynamics. Failed, missing or stale measurements use original volume; the 17 failed analyses do not prevent playback. Rerunning the measurement command retries them.

Both the library service and Apple TV app need the update. In **administrator PowerShell**, from your current Windows checkout:

```powershell
git pull --ff-only
.\scripts\windows-update-service.ps1
```

The updater builds the current server package, installs it in the configured service Python, and restarts the task if it was running. It retains the existing ProgramData database, measurements, pairing sessions, provider settings and media. It checks `/health` for the new version. Use `-State` for a nonstandard installed state directory. Server **0.9.1** isolates installation from Python settings left by maintenance scripts and works with Apple TV **0.9.0 (6)**. Install that Apple TV build through TestFlight. No rescan or repeat of successful audio analysis is needed.

The audio tap applies gain to decoded samples; it does not rewrite videos or require an additional normalized conversion cache. Multi-audio MP4s use a remuxed copy of their first audio track so playback matches the measurement. Existing format-compatibility conversions still apply. See [normalization behavior, limits and verification](docs/normalization.md).

#### Measure audio loudness

The server includes a resumable audio measurement command for volume normalization. It measures each available, indexed video's entire first audio track using FFmpeg's [EBU R128 loudness analysis](https://ffmpeg.org/ffmpeg-filters.html#loudnorm), and saves integrated loudness (LUFS), true peak (dBTP), loudness range (LU), and gating threshold. Apple TV 0.9.0 applies validated measurements during playback when connected to the updated service.

On the Windows PC, run from an updated mvideo source directory. The launcher uses that checkout's Python environment when present, or reuses the installed service's Python environment:

```powershell
.\scripts\windows-measure-loudness.ps1             # measure the indexed library; resume on subsequent runs
.\scripts\windows-measure-loudness.ps1 -Status     # saved coverage; no audio decoding
.\scripts\windows-measure-loudness.ps1 -Limit 10   # small batch before running the whole library
```

The launcher reads `background.json` in the installed ProgramData state directory to use the service's library, FFmpeg paths, and fallback Python executable. A separate checkout (for example `C:\_code\mvideo`) can therefore use the service environment at `L:\mvideo-service` while running the scanner source from the new checkout; there is no need to install another environment or rescan an already indexed library. It also supports an interactive installation, `MVIDEO_STATE`, explicit `-Library` / `-State` paths, and `-PythonPath` to select an existing Python 3.12+ executable with mvideo's dependencies. No provider credentials, service restart, or Apple TV update are required to measure audio. If the catalog needs updating, run `scripts/windows-start.ps1 -Scan` from the installed service checkout with the same library/state configuration.

The portable CLI uses the usual `MVIDEO_LIBRARY`, `MVIDEO_STATE`, `MVIDEO_FFMPEG`, and `MVIDEO_FFPROBE` settings:

```sh
.venv/bin/mvideo --env .env measure-loudness
.venv/bin/mvideo --env .env measure-loudness --status
.venv/bin/mvideo --env .env measure-loudness --limit 10
```

- One video is processed at a time with one audio decoding/filter thread; Windows FFmpeg processes run below normal priority. Full-library analysis must read every audio track and may take hours. Progress is printed before and after each video.
- Each result is committed immediately to `audio_loudness` in the existing `library.sqlite3` (normally `C:\ProgramData\mvideo\library.sqlite3`). **Ctrl+C** stops the scan; rerunning resumes by skipping unchanged completed measurements. The originals are never written, tagged, or replaced, and no converted media copies are generated.
- Measurements record source size/mtime, analysis profile, FFmpeg version, audio stream index, and timestamp. A changed source or analysis profile is remeasured. Run the ordinary catalog scan after replacing files; an unindexed change produces an error instead of saving a measurement against an old file version. Coverage status reflects the indexed catalog, not a fresh filesystem scan.
- Silent or below-gate tracks and videos without audio are recorded separately, with no invented loudness/gain. Decode failures and timeouts are recorded, later videos continue, and failed files retry on the next run. Two loudness scans cannot run against the same state directory simultaneously.
- Use `-Force` / `--force` to remeasure completed videos. `-Limit N` / `--limit N` counts attempted files, including failures, but excludes cached results. `-TimeoutSeconds N` / `--timeout N` changes the default 1,800-second analysis timeout per video. Exit codes: 0 for a successful batch, 1 for failures/deferred results, 130 for interruption.

Analysis uses the first audio stream, converted to a defined stereo/48 kHz mix before measurement; the profile is `first-audio-stereo-48k-r128-v1`. Only the filter's **input** measurements are retained, so the playback target does not require another scan. The native player uses measured peak headroom and a final sample guard; see the normalization notes for the limits of source measurements after AAC conversion and device mixing.

#### Playback behavior

The server uses actual FFprobe stream metadata, not extensions. Conservative first-generation Apple TV 4K baseline: progressive H.264 up to 1080p/60, 8-bit 4:2:0 and AAC-LC stereo in MP4 plays directly. Compatible streams in other containers are remuxed; incompatible audio/video receives a cached H.264/AAC MP4 derivative. Interlaced material is deinterlaced; sample aspect ratio is preserved. HDR needs explicit compatibility review and is not silently converted to washed-out SDR.

Conversions run one at a time and must finish before playback, enabling full-file byte-range seeking. Initial conversion can take time, especially 4K VP9. Original files remain unchanged. Native playback prefetches the next queue item. HLS/adaptive renditions are evaluated in the plan but are not currently implemented. Cache outputs are pinned while media tickets remain valid; old unpinned outputs are evicted. A full cache reports a recoverable conversion error.

A queue snapshots all matching IDs, not just the visible page. Shuffle is a permutation without repeats. Selecting a video starts there and wraps through the rest of the same scope once. At exhaustion the app can offer replay. Deleted/unavailable items produce explicit retry/skip behavior.

App 0.6.0 adds a shortcut: while a video is playing with the playback controls hidden, **double-tap the right edge of the Siri Remote touchpad** to skip to the next video. A single right tap keeps the native seek behavior. When the controls or Up Next are open, rightward input navigates them normally; **Next video** is also available in the playback controls. Skipping the last video ends the selection and offers **Play again**.

## Apple TV and TestFlight

The dedicated app is **mvideo - music videos**, bundle `com.soundtrackgeek.mvideo`, Apple team `3L5769JKCM`, minimum tvOS 18. Its session lives in Keychain service `com.soundtrackgeek.mvideo`; provider keys never reach the app. The shorter App Store name was already taken. [App Store Connect](https://appstoreconnect.apple.com/apps/6818073365/testflight/tvos).

Install mvideo through its TestFlight invitation, open Tailscale on Apple TV and connect to your tailnet, then enter the HTTPS origin above and a fresh eight-digit code from the Windows pairing command. Use Connection in the navigation bar to disconnect or pair again. The owner has installed, paired and played videos on the physical Apple TV. App Store Connect reports Apple TV 4K on tvOS 26.6; its generation is believed to be first-generation but remains unverified.

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
