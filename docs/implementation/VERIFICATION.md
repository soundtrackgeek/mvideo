# Verification — updated 2026-10-03

## Installed Windows service

The independent mvideo **0.9.1** service uses the Python environment at `L:\mvideo-service`, reads `L:\MusicVideos`, and stores runtime data under `C:\ProgramData\mvideo`. Python 3.13 and `C:\ffmpeg\bin` are used. The current package was built from the Windows checkout and installed as a wheel; the older service source directory is no longer the imported editable package.

The **mvideo Library** scheduled task is running as Local Service (`S-1-5-19`) with an `MSFT_TaskBootTrigger`, 30-second startup delay, failure restart and no execution time limit. It requires no interactive login. State/code ACLs and encrypted machine-DPAPI provider loading were installed with owner-approved administrator access. A fresh task launch and HTTPS health response passed. An actual Windows reboot was not performed. Tailscale's Windows service is Automatic.

Private HTTPS `https://jorncomputer.tail5ef358.ts.net:8443` forwards to `127.0.0.1:8765`. Tonehavn's port 443 route remains unchanged. No Funnel/public access was enabled. The native simulator paired over this HTTPS route and saved its session in the separate mvideo Keychain namespace.

## Real library and media verification

Full Windows scan: **15,559 indexed and probed videos**, zero pending/inaccessible files. Extension counts: 15,065 MP4, 301 WebM, 182 MPG, 7 AVI, 2 MKV, 1 VOB, 1 WMV. Codec policy classifies 15,005 direct, 513 video transcode and 41 audio transcode. There are 114 conservative filename-review warnings and 28 unknown years. These are metadata review states, not missing videos.

Sixteen initial real-file probes identified H.264/AAC, MPEG-1/2 + MP2, 4K VP9/Opus, MPEG-4 ASP/MP3, VP9/AAC, interlaced PAL MPEG-2/AC-3 and WMV2/WMAv2. Actual codecs establish the playback mode; extension alone is insufficient.

One real file from **each of the seven formats** subsequently passed Windows HTTPS playback preparation, initial/suffix byte ranges, FFprobe validation and FFmpeg decoding at the start, midpoint and near the end. MP4 played directly; the six other sampled formats used Windows-generated H.264/AAC derivatives. Source size and modification time remained unchanged. The verification session was revoked afterwards. Separately, local real-media conversions checked display aspect ratio, and generated integration fixtures verified remux, audio conversion, anamorphic transcoding, thumbnails and source preservation.

A Windows shuffle queue returned **15,559 unique IDs**, covering the entire selection. Machine-local evidence is in ignored `output/windows-verification.json`, `output/codec-samples.json` and `output/media-verification/results.json`. These are representative decode checks, not a claim that every video was played end to end. Audio tracks and audio decoding were verified; physical speaker output/listening remains unverified.

## Providers and home artwork

Verified library identities were installed for a-ha, Duran Duran and Tears for Fears. Each returned a real Last.fm biography and fanart.tv images over authenticated HTTPS; image fetches returned HTTP 200. Twelve featured-image requests sampled all three artists. The native home screen visibly rendered a Tears for Fears background, artist attribution and real catalog thumbnails, with 15,559 videos shown.

Home chooses a random available background from matched library artists once per launch, retains it during navigation and falls back to a library thumbnail. In 0.4.1, opened artist pages and visible artist tiles automatically match artists using MusicBrainz recording credits; manual mappings remain available for unresolved names. The whole artist library has not been identity-matched or crawled. Provider credentials remain server-only, encrypted on Windows, and were not bundled in the app.

## Automated and native verification

- **20 server tests passed** (`.venv/bin/pytest server/tests -q`, 16.38 seconds): conservative parsing, Unicode/punctuation and case-insensitive artist scopes, offline/partial/deleted scans, 15k pagination/shuffle, revision conflict, pairing/lockout/revocation, media authorization and ranges, traversal prevention, featured-artwork selection, codec policy and FFmpeg integration. One dependency deprecation warning, no failures.
- **8 native tests passed, zero skips**, against the real Windows HTTPS service on the tvOS 26.5 Apple TV 4K simulator: five model/origin/queue tests, live AVPlayer seeking/audio-track/automatic-next integration, and two remote-navigation tests covering tabs, native keyboard, playback dismissal, restored focus and scroll position.
- Native result bundle: `test_sim_2026-10-01T08-42-38-001Z_pid66859_61ccbd72.xcresult` under the local XcodeBuildMCP workspace. Verified home screenshot: ignored `output/mvideo-home.jpg`.
- Release archive/export succeeded with stable Xcode 26.6. Exported IPA passes `codesign --verify --deep --strict`; application identifier is `3L5769JKCM.com.soundtrackgeek.mvideo`, team is `3L5769JKCM`, and `get-task-allow` is false.

## 0.4.0 UI update verification

- **21 server tests passed** (15.59 seconds), including a new facet-artwork regression covering year/decade/artist scope, pagination/search, verified cached artwork, no provider crawl and revoked image tickets.
- All **10 distinct native tests passed with zero skips** across the full run and targeted rerun. The initial photo test exposed a parent accessibility identifier overriding the viewer controls; removing that identifier fixed the test. The final targeted rerun passed photo reachability, section separation, full-screen opening, next-image navigation, dismissal/return focus, plus real AVPlayer playback, metadata title, seeking and automatic next.
- Visually inspected simulator screenshots of artist/year/decade image tiles and the a-ha photo row/viewer. Video thumbnail bounds remain stable across source aspect ratios. Artwork comes from real scoped library videos or cached verified fanart.tv photography.
- Updated the existing Windows boot task's service source and restarted it. HTTPS health reports **0.4.0**. **20 real artwork requests** succeeded: six artist fallback stills, a-ha fanart.tv, six early years and all seven decades. The temporary verification session was revoked. No media, pairing sessions or boot configuration were replaced.
- Local evidence: `output/artwork-verification.json`, `output/ui-0.4.0/`, `output/gallery-0.4.0/`. Final targeted result: `test_sim_2026-10-01T09-30-02-891Z_pid66859_3d5c1716.xcresult` in the XcodeBuildMCP workspace.
- Release 0.4.0 (2) archived and exported with Xcode 26.6, passed strict signature/entitlement verification, and uploaded successfully to App Store Connect.
- Native controls use **Artist - Track (Year)**; missing artist/year values are omitted, with unit coverage for incomplete metadata and a live check of AVPlayerItem's title metadata.

## 0.4.1 artist-artwork correction

- Root cause: only three manual artist identities could use fanart.tv, and the Artists grid read existing cached images without initiating lookup. Most artists therefore retained video stills indefinitely.
- Added automatic MusicBrainz matching from exact artist/alias and library-song recording credits, followed by fanart.tv and Last.fm. Conflicting identities, collaborations and truncated searches remain unresolved; manual mappings take precedence.
- Missing artwork now resolves through one background worker with at most 64 pending artists. Visible tiles and artist pages poll until the cached result is ready, without blocking navigation. Old manual-only negative entries are reconsidered immediately. Provider errors preserve already available biography/photo data and use a shorter retry cache.
- **36 server tests passed** after the final provider retry correction. Coverage includes ambiguous/wrong-song matches, aliases, truncation, manual overrides, old negative caches, nonblocking/deduplicated lookup, library-only requests, signed/revoked image access, and Last.fm errors/rate limits that must not block fanart.tv. One existing dependency deprecation warning.
- **11 distinct native tests passed, zero skips**, across the ten-test smoke run and the new automatic-artwork UI test against Windows. The latter verifies newly matched 10,000 Maniacs photos and fanart.tv grid attribution. Visual inspection confirmed the artist-page hero switches to the band photo and the grid shows photography for ’Til Tuesday, 10 Years and 10,000 Maniacs.
- Five real Windows automatic matches returned photos and downloadable image bytes: ’Til Tuesday (2), 10 Years (12), 10,000 Maniacs (3), Matchbox Twenty (7), Alanis Morissette (12). No manual mappings were added for these artists. A separate local test of `(hed) p.e.` / `Represent` found no exact recording match and correctly retained the fallback. This is not a claim of complete provider coverage.
- Evidence: ignored `output/windows-matching-verification.json`, `output/matching-verification.json`, `output/artwork-0.4.1/`, `output/artist-fanart-0.4.1.jpg`. Automatic-artwork UI result: `test_sim_2026-10-01T09-55-39-157Z_pid66859_a5c156cf.xcresult` in the local XcodeBuildMCP workspace.
- Stable Xcode 26.6 archive and App Store export succeeded for **0.4.1 (3)**; the exported IPA passed strict code-signature verification. Distribution uses the existing archive-without-development-signing, distribution-sign-at-export workflow because no physical development device is registered.

## 0.5.0 playlists and browser editor

- **45 server tests passed** (21.62 seconds), including nine playlist cases covering atomic writes, persistence, validation, optimistic conflicts, missing/unavailable videos, paging and complete ordered/shuffled queues, authentication, packaged editor assets and one-time seeding that preserves later edits/deletions. One existing dependency deprecation warning.
- **Three browser logic tests passed**, and the production Vite build completed. The Python wheel contains the compiled editor and starter recipes; Windows needs no Node.js runtime.
- **Eleven targeted native tests passed with no skips in their final runs**: seven core model/origin/queue tests, live AVPlayer seeking/audio/automatic-next integration, full remote navigation/return focus, the new playlist overview/detail/playback/return-focus test, and automatic artist photography after the added navigation tab. An unsigned regression attempt could not access the paired simulator Keychain and skipped; rerunning with the normal signing configuration passed. The live tests used the actual Windows HTTPS service on the tvOS 26.5 Apple TV 4K simulator.
- Browser/IAB checks covered pairing, creating, searching, adding, rename, save/reload, drag reorder and persistence on a separate catalog copy. Fixed native image drag interference and drag-enter/drop event handling. Desktop 1536 × 1024 and mobile 390 × 844 were visually inspected; no horizontal document overflow. Final HTTPS pairing, real thumbnails, search and all three production playlists were verified. The [design comparison](../design/PLAYLIST-STUDIO.md) records the concept, screenshots, copy differences and responsive adaptations.
- Backed up the Windows database with SQLite's backup API to `C:\ProgramData\mvideo\backups\before-playlists-0.5.0.sqlite3`, upgraded the service source, installed the starters and restarted the existing boot task. HTTPS health reports **0.5.0**. Catalog remains **15,559** videos. Eurodance has **37** available videos, Glam metal & hard rock **42**, and Chart toppers **24**; all matched their intended recipes. Ordered queues and full shuffled membership passed authenticated live checks. See [track lists and chart sources](../playlists.md).
- Evidence: ignored `output/playlist-live-verification.json`, `output/playlist-live-native.log`, `output/playlist-native-tests.log`, `output/playlists-tvos/`; native live result `output/PlaylistDerivedData/Logs/Test/Test-MVideo-2026.10.01_14-53-52-+0200.xcresult`.
- The temporary API verification session was revoked after live checks. The delivered browser tab retains its own paired session. Disposable local QA records were removed.
- Stable Xcode release archive and App Store export succeeded for **0.5.0 (4)**; the IPA passed `codesign --verify --deep --strict`. Upload succeeded at 15:00 Europe/Oslo. Archive and export are in ignored `output/MVideo-0.5.0.xcarchive` and `output/export-0.5.0/MVideo.ipa`.

## 0.6.0 remote skip shortcut

- Added a two-tap right-arrow recognizer to the native player, with priority over the single-tap recognizer. Playback controls, presented menus and focus inside Up Next retain normal navigation. The recognizer is removed with the player and ignores preparation, errors and finished selections.
- **11 targeted native tests passed, zero failures and zero skips** in the final run on the paired tvOS 26.5 Apple TV 4K simulator using the real Windows library. Coverage includes single-right and double-left inputs retaining the current video, double-right advancing exactly once, rightward navigation with controls open, last-item exhaustion, AVPlayer seeking/automatic next, and library return focus/scroll position.
- An earlier run timed out on the existing scroll-position restoration assertion; its targeted rerun and the final combined run both passed without changing that behavior or assertion.
- Final result: `test_sim_2026-10-01T13-33-46-871Z_pid63653_d37875d7.xcresult` in the local XcodeBuildMCP workspace (81.4 seconds). Simulator playback screenshot inspected in ignored `output/double-tap-screenshots/`.
- App source version is **0.6.0 (5)**. This change has not been uploaded to TestFlight. Automated remote checks synthesize directional presses; light double-tapping on the physical Siri Remote still needs verification.

## 0.7.0 loudness measurement script

- Added `mvideo measure-loudness` and `scripts/windows-measure-loudness.ps1`. Measurements are committed per video to the existing database, independent of playback preparation. Only audio is decoded; filter output is discarded. The Windows launcher uses installed background configuration without reading provider secrets.
- **55 server tests passed** (21.64 seconds), including ten new loudness tests and the existing real-media playback tests. One existing dependency deprecation warning. Coverage includes persisted resume, force/batch behavior, source/profile invalidation, changes during analysis, concurrent catalog updates, interruption/lock release, offline libraries, path containment, failure/timeout handling, CLI exit codes, and nonfinite/silent measurements.
- Real FFmpeg fixtures confirmed a known 20 dB difference in integrated loudness and true peak, selection of the first of two audio tracks, separate silence/no-audio states, unchanged source hashes and mtimes, and no generated playback media.
- The actual CLI measured **two existing local video samples** from `output/media-verification/playback`, saving **-14.48 LUFS / +0.13 dBTP** and **-23.15 LUFS / -7.50 dBTP**. `--status` reported two measured and ten pending files in the isolated local smoke catalog. Evidence is in ignored `output/loudness-smoke/library.sqlite3`.
- The scanner was exercised on macOS with FFmpeg. The PowerShell launcher and Windows process-priority path have not been executed on Windows. The production library has **not** been measured or this server update deployed. Apple TV playback does not yet consume the measurements; no TestFlight build was created for this script.

## 0.7.1 loudness launcher environment fix

- Fixed the missing-environment error reported from `C:\_code\mvideo`: a checkout without `.venv\Scripts\python.exe` now falls back to the executable recorded in the installed service's `background.json`. `PYTHONPATH` continues to select scanner code from the invoking checkout. An explicit `-PythonPath` overrides both choices.
- **Seven PowerShell execution checks passed** using a portable PowerShell 7.6.6 runtime on macOS: separate-checkout/service-environment fallback, paths containing spaces and argument forwarding, local-environment priority, explicit override, missing-interpreter diagnostics, native exit-code propagation, and actual `mvideo measure-loudness --status` execution from a separate checkout. Checks used disposable directories and isolated state; they did not touch the Windows service or production library. Reproduction harness: ignored `output/powershell-qa/check_launcher.py`.
- This validates launcher execution and interpreter/source selection under PowerShell; native Windows execution remains to be confirmed by rerunning the updated script on the PC.

## 0.8.0 filename repair command

- Audited all **15,559** filenames through the mounted Windows media share. The original parser flagged 114 filenames. The reviewed plan contains **183 renames and one move aside**, including six explicit year decisions from the owner and the unknown-year Matt Cox video. Projecting the final plan across the complete inventory leaves **15,558** names with zero parser warnings and no destination collisions. Full names, decisions and identification sources are in [the audit](../filename-repairs.md).
- **77 server tests passed**, including 22 filename-repair cases: all 184 bundled actions on a disposable library, preserved contents/mtime, playlist order/version and foreign keys, metadata overrides, searchable corrected metadata, retained loudness measurements, idempotence, locks, Unicode path matching, invalid plans, destination conflicts, changed sources, symlinks, interrupted filesystem moves, automatic-scan reconciliation and restoration followed by a later year correction.
- **Nine real PowerShell checks passed** under portable PowerShell 7.6.6 on macOS. Seven existing loudness-launcher checks still pass after sharing Python/configuration discovery; two additional checks execute the filename preview and custom-plan apply through the actual CLI. Paths with spaces and a separate checkout/service environment were exercised. Reproduction harness: ignored `output/powershell-qa/check_launcher.py`.
- Production media has **not** been renamed or moved. The mounted L share is readable, but the live database is at `C:\ProgramData\mvideo\library.sqlite3` and remote Windows command access was unavailable. Apply the command on the Windows PC, then verify its summary and refresh the Apple TV library. Native Windows filesystem execution remains to be confirmed there; no service or TestFlight deployment was performed.

## 0.9.0 on-device volume normalization

- Owner-reported completed analysis on 2026-10-02: **15,541 current measurements, 17 errors, zero pending/stale**, across **15,558** videos. Normalization uses those stored measurements, with original-volume fallback for unusable records.
- **96 server tests passed**, including 19 new gain/API/first-track cases and a real FFmpeg multi-audio MP4 remux. Source bytes remain unchanged. Authenticated responses supply bounded gain only for matching file/profile/stream measurements.
- **11 native tests passed** on tvOS 26.5 Simulator using Xcode 26.6: eight existing core tests and three normalization tests. The generated MP4 is served over actual loopback HTTP with byte ranges. The test verifies the real audio tap's positive/negative sample gain, unity when disabled, seeking, automatic next, no inherited gain for an unmeasured item and persisted preferences. An initial assertion raced the silent preroll buffer; the test now waits for actual nonzero source samples. Final result: ignored `output/normalization-native-tests.log` and `output/NormalizationDerivedData/Logs/Test/`.
- **Four updater PowerShell checks passed** with mocked Task Scheduler/pip/health on macOS: update/restart of a running service, preservation of a stopped service, package-build failure before stopping, and restart after an installation error. A real server wheel built successfully; it includes the normalization module and bundled data. Native Windows deployment is recorded below.
- Release **0.9.0 (6)** archived and distribution-signed/exported successfully. Artifacts: ignored `output/MVideo-0.9.0.xcarchive` and `output/export-0.9.0/MVideo.ipa`. Upload/processing and installed-device behavior are separate checks; see delivery status below.

## 0.9.1 Windows deployment and live verification

- Running the updater in the existing Windows administrator session exposed inherited `PYTHONPATH` from maintenance commands: pip saw the checkout's newly built metadata and incorrectly considered 0.9.0 installed while HTTPS still reported 0.5.0. The updater's health check caught this. Isolated Python (`-I`) and forced wheel reinstallation fixed the environment ambiguity; four updater checks and all 19 normalization server tests passed again.
- Pulled the fix into `C:\_code\mvideo`, built and installed **0.9.1** in the existing service environment, and restarted the existing scheduled task. Both the updater's loopback check and an independent private HTTPS `/health` request confirmed **0.9.1**. A subsequent Windows loudness status check retained **15,541 measured / 17 errors / zero pending or stale / 15,558 total**.
- The native real-library playback test passed with zero skips against the updated Windows HTTPS service. It verifies saved gain reaches the actual audio processor, supported PCM and processed frames after seeking, and a fresh normalization processor on automatic next. The paired simulator Keychain session remained usable. This brings current native coverage to **12 distinct passing tests**, including the 11 core/normalization tests above. Evidence: ignored `output/normalization-live-native.log` and `output/NormalizationDerivedData/Logs/Test/Test-MVideo-2026.10.02_12-52-51-+0200.xcresult`.
- Physical-device listening and comparison across different songs still require owner feedback; simulator audio processing and TestFlight installation do not establish the sound at the television/speakers.

## 0.10.0 artist navigation and picture-in-picture

- The library owns one playback session across full-screen playback, the in-app floating player and native system PiP. **Go to artist** opens the current artist without replacing the AVPlayer, item or queue; videos without an artist omit the action.
- **19 model/playback tests** cover HTTP audio continuity through artist navigation and restoration, normalization, seeking, automatic next, changed artists, native PiP restore versus close, failed PiP startup, stale callbacks and Menu dismissal. The optional live Windows-library seek/automatic-next test ran and passed.
- **Four remote UI tests** cover the artist action and floating player, Back/full-screen return, original focus and scroll position, double-right skip, and playlist playback. The artist test resumes playback before navigating. Reference scroll positions are captured after tvOS finishes its focus animation.
- Debug simulator and unsigned Release device builds pass with Xcode 26.6. Built app metadata is **0.10.0 (7)** and includes the `audio` background mode. Local evidence is in ignored `output/pip-verified.xcresult`, `output/pip-verified.log` and `output/pip-release-verified.log`.
- Native PiP callbacks are regression-tested, but the actual system PiP window and background/restore/queue transitions still require a physical Apple TV. Use [Apple's standard-player PiP guidance](https://developer.apple.com/documentation/avkit/adopting-picture-in-picture-in-a-standard-player) for device verification. No TestFlight upload or Windows service update is included in this source change.

## 0.10.1 Windows launcher recovery — 2026-10-03

- The owner reported Library unavailable while the PC was on. Both the PC and Apple TV were online in Tailscale. The **mvideo Library** task was **enabled but stopped** (`Ready`, last result `1`), with no listener on port 8765. Tailscale remained Running/Automatic and its private HTTPS forwarding was intact. The PC had not rebooted since September 30. The task's October 2 last-run timestamp identifies its launch, not the time it failed.
- Both service logs were empty and Task Scheduler operational history was disabled, so the original triggering error and exact failure time could not be recovered. On this PC's **Windows PowerShell 5.1.26100.9549**, an isolated harmless Python stderr message reproduced `NativeCommandError` with the original launcher's strict error preference. The full original launcher exited `1`, omitted the message from its log, and did not reach the Python completion marker.
- **Three isolated Windows launcher regression cases passed**: the original launcher reproduced the failure; the corrected launcher retained stderr and completed with exit `0`; a deliberate Python failure retained stderr and propagated exit `7`. Tests used temporary media/state directories and a stub module, without scanning or modifying production media.
- Deployed the corrected launcher to `L:\mvideo-service\scripts\windows-run-background.ps1`, retaining the existing task/account, provider configuration, catalog, measurements and sessions. The earlier launcher is backed up at `C:\ProgramData\mvideo\backups\launcher-before-0.10.1-20261003.ps1`. Installed and repository script SHA-256 hashes match. The task was Running/Enabled after restart, and both loopback and private HTTPS health checks confirmed the unchanged server package **0.9.1**. This is a launcher patch; no new TestFlight build was needed.
- Restart readiness was slow (roughly 25 seconds on the first launch and about a minute on the deployment launch). The latter Python process started about 46 seconds after the task, so this delay is not established as purely scanning. Subsequent HTTPS health responses took approximately 30–40 ms. Read-only local timing measured the Home query at 26 ms, the full 15,558-video queue query at 85 ms and the reported video's initial file read at 1 ms.
- The existing live playback/seek/automatic-next test passed against Windows. A Home UI attempt before deployment failed to load its first video within 20 seconds; after deployment the complete Home → playback → artist → full-screen UI test passed. The new live Home/queue test passed without skips: Home took 4.14 seconds, the 15,558-video queue 0.43 seconds, and **'Til Tuesday — (Believed You Were) Lucky** playback preparation 0.029 seconds. Timing logs contain no session credentials or ticketed URLs.
- After the first task start, the owner confirmed browsing returned but reported playback request timeouts. After deployment, service restart and fully reopening mvideo, the owner confirmed **playback starts on the physical Apple TV**. The precise cause of those transient request timeouts is not established separately from recovery; the reproduced launcher defect is fixed, while the original stderr trigger remains unknown.
- Local evidence is in ignored `output/incident-20261003/`: initial task/configuration diagnostics, Windows regression results, deployment verification, query timings, native playback and Home UI test logs/results.

## 0.10.2 automatic TestFlight workflow — 2026-10-03

- GitHub inspection found no Actions workflows, workflow runs, repository secrets, environments or self-hosted runners. Previous commits therefore had no GitHub Actions upload path; 0.10.0 had been built locally without a TestFlight upload.
- Configured [TestFlight — master in Xcode Cloud](https://appstoreconnect.apple.com/teams/b1e1e3ed-bd76-448e-bf6c-7211ea008199/xcode-cloud/products/B323A525-603A-4250-8F9F-A62E0CFCC703/workflows/07226CB5-6E9A-4728-9B1D-F237016B9E9E) using the existing Apple/GitHub repository connection. It starts for changes to **master**, with **any file change** eligible and older builds automatically cancelled. Its archive action targets **tvOS TestFlight (Internal Testing Only) distribution**, the committed **MVideo** project/shared scheme and **Xcode 26.6**. Saved the **TestFlight Internal Testing** post-action for **mvideo testers** (one member) and set the next Cloud build number to **8**. No additional repository-access grant or signing secrets were needed. The first successful automatic build/delivery remains pending verification.
- Independently archived and uploaded Apple TV **0.10.0 (7)** with the existing local Xcode account. Upload succeeded at **10:21:06 Europe/Oslo on 2026-10-03**, and Apple processing completed. Added the build to the existing **mvideo testers** internal group; its Builds tab shows **Testing** with 90 days remaining. The Testers tab separately confirms **Installed 0.10.0 (7)** on **2026-10-03**, on the tester's **Apple TV 4K / tvOS 26.6**. This manual delivery does not establish Cloud build success.
- The app marketing version remains **0.10.0**; this repository release documents automation and does not change the Windows server package **0.9.1**. Cloud assigns its own increasing build numbers.
- The first code push (`d8a1352`) automatically triggered Cloud build **8**. Archive and App Store export succeeded, but development/ad-hoc exports failed because the team has no registered tvOS devices for those profiles. Changed Distribution Preparation to **TestFlight (Internal Testing Only)** and are verifying a new push; this setting has not yet been proven to avoid those exports. Downloaded logs are in ignored `output/testflight-20261003/cloud8/`.
- Local evidence: ignored `output/MVideo-0.10.0.xcarchive`, `output/testflight-20261003/archive.log` and `output/testflight-20261003/upload.log`.

## TestFlight delivery

Dedicated app **mvideo - music videos**, App Store Connect ID **6818073365**, bundle **com.soundtrackgeek.mvideo**. The plain name mvideo was unavailable. No existing app identity was reused.

Latest delivery: **0.10.0 (7)**, accepted at **10:21:06 Europe/Oslo on 2026-10-03**, with Apple processing complete. The **mvideo testers** group's Builds tab shows **Testing** with 90 days remaining. Its Testers tab confirms **Installed 0.10.0 (7)** on **2026-10-03**, on **Apple TV 4K / tvOS 26.6**. The configured Cloud workflow's first successful automatic delivery remains unverified.

Previously verified delivery: **0.9.0 (6)** uploaded successfully at 12:41 Europe/Oslo on 2026-10-02, completed Apple processing, and was added to the existing internal **mvideo testers** group. Release testing notes were saved. App Store Connect then showed one tester and five builds and reported **Installed 0.9.0 (6)** on the tester's **Apple TV 4K / tvOS 26.6**. Release confirmation is saved locally in ignored `output/testflight-0.9.0.jpg`.

The requested account **jtillnes2@yahoo.com** already belonged to this Apple team and was added as a tester without changing its account permissions. The invitation was accepted previously. The owner confirmed earlier installation, pairing and working playback, supplied photos of its browsing and player UI, and reported missing artist photography after updating. The current installation is confirmed above; normalization and other recent features still need owner behavior/listening feedback on the physical device.

Latest local distribution artifacts: ignored `output/MVideo-0.10.0.xcarchive` and the successful upload log `output/testflight-20261003/upload.log`. [App Store Connect](https://appstoreconnect.apple.com/apps/6818073365/testflight/tvos).

## Reference and provider decisions

Tonehavn runs its server on loopback port 3210 behind HTTPS. Its iOS client validates an origin-only HTTPS URL, uses native URLSession/AVPlayer, and keeps account secrets out of UserDefaults. mvideo follows this separation with its own loopback service, explicit HTTPS origin and Keychain namespace. No Tonehavn source/configuration was modified.

Sources checked 2026-10-01:
- [Apple TV 4K first-generation specifications](https://support.apple.com/en-tm/111929). Owner believes this is the target model; generation remains unverified; App Store Connect reports Apple TV 4K on tvOS 26.6, and basic device playback is owner-confirmed.
- [Apple HLS authoring specification](https://developer.apple.com/documentation/http-live-streaming/hls-authoring-specification-for-apple-devices/).
- [FFmpeg format documentation](https://ffmpeg.org/ffmpeg-formats.html). Completed MP4 VOD selected initially for reliable seek coverage; HLS remains a future optimization.
- [Last.fm artist.getInfo](https://www.last.fm/api/show/artist.getInfo): public API key required, user authentication/shared secret unnecessary, MusicBrainz UUID supported, error 29 is rate limiting.
- [Last.fm API terms](https://www.last.fm/api/tos): attribution and links retained. Personal use only in this milestone; broader/commercial distribution requires revisiting provider terms.
- [Official fanart.tv API client](https://github.com/fanart-tv/fanart.tv-api): music uses MusicBrainz artist IDs; project key required, personal client key optional, 429 backoff. Conservative one-request/second local budget is an application policy, not a claimed published quota.
- [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) and [search documentation](https://musicbrainz.org/doc/MusicBrainz_API/Search): recording/artist credits support automatic identity matching; an identifying User-Agent and at most one request per second are required. [fanart.tv API](https://api.fanart.tv/) confirms the artist endpoint uses MusicBrainz artist UUIDs.

## Release gates

| Gate | Status |
| --- | --- |
| Full real Windows catalog/probes | 15,558 after naming cleanup; 15,541 loudness measurements, 17 analysis errors, zero pending/stale |
| Boot service configuration and fresh task launch | Verified Local Service, no login; actual reboot untested |
| Private HTTPS and pairing | Verified Windows route and native Keychain |
| Representative seven-format playback and seeking | Passed through Windows HTTPS; originals unchanged |
| Live Last.fm/fanart.tv and random home image | Verified for three manual identities; automatic fanart.tv matching and image bytes verified for five more artists |
| tvOS simulator build/navigation/playback | Nineteen model/playback tests and four remote UI tests passed for 0.10.0; native system PiP needs physical-device verification |
| Physical Apple TV | Owner-confirmed playback after launcher recovery; App Store Connect confirms 0.10.0 (7) installed on Apple TV 4K / tvOS 26.6; native system PiP still needs device verification |
| Signing/archive/export/upload | 0.10.0 (7) manual archive/upload passed; dedicated identity |
| Apple processing | 0.10.0 (7) complete |
| TestFlight build/group | 0.10.0 (7) Testing in mvideo testers; installation confirmed |
| Automatic Cloud delivery | Master push workflow and internal-group post-action configured; next build 8; first successful delivery pending verification |
| Requested invitation | jtillnes2@yahoo.com accepted; 0.10.0 installation confirmed by App Store Connect |

Remaining physical-device checks: compare normalization on/off across songs, including quiet and loud sources, seeking and continuous transitions. Shared playlists, artwork and double-right skip should also be confirmed on the physical remote. A future reboot should confirm the configured boot trigger in practice.
