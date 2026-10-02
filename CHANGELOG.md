# Changelog

## [0.9.2] - 2026-10-02

### Added

- README maintenance procedure for adding/replacing videos, indexing through the installed Windows environment, measuring loudness, checking coverage and reloading Apple TV.
- Exact custom rename-plan instructions to preserve measurements and playlist references, plus recovery steps for files already renamed manually and an explanation of automatic playback gain versus manual loudness analysis.

## [0.9.1] - 2026-10-02

### Fixed

- Isolate the Windows service updater from inherited Python settings after a loudness scan, so checkout metadata cannot make pip incorrectly skip the installed service update. Reinstall the built wheel even when its version matches.
- Server package version is 0.9.1; the compatible Apple TV release remains 0.9.0 (6).
- Live Windows playback verification now requires the saved gain to reach the native audio processor through seeking and automatic next.

## [0.9.0] - 2026-10-02

### Added

- On-device Apple TV volume normalization using the saved first-audio loudness measurements. A native audio tap applies per-video gain before playback, targeting -18 LUFS with measured true-peak headroom and a +12 dB boost ceiling.
- Persistent, enabled-by-default **Normalize volume** player control with smooth switching, per-item reset and original-volume fallback for missing, failed, stale or unsupported measurements.
- Authenticated playback responses with validated normalization metadata, plus a Windows server-package updater that retains the installed state and restarts a running service after installation.
- Native HTTP playback tests for actual sample gain, seeking, automatic next, missing measurements and preference persistence; server tests for gain constraints, stale/failed records and real first-audio-track remuxing.

### Changed

- MP4 files with multiple audio tracks now use the existing remux path to expose only the measured first track to Apple TV.
- Server and tvOS source version is 0.9.0; Apple TV build number is 6. Source media is unchanged and normalization does not create new audio conversions.

## [0.8.0] - 2026-10-01

### Added

- Full 15,559-file naming audit and explicit repair plan with 183 renames, six owner-supplied year corrections, and a temporary move aside for the unknown-year Matt Cox video.
- Preview-first `mvideo fix-filenames` command and Windows launcher. Explicit apply backs up SQLite, preserves source content/mtime, migrates playlist references, overrides, search and loudness measurements, and journals each move for interruption recovery.
- A sibling Needs Review folder for explicitly listed videos, with unavailable catalog entries retaining their references for later restoration. Conflicting destinations, changed sources and concurrent library/loudness scans block repairs.
- Regression coverage for the entire bundled repair plan, references and cached measurements, collision handling, interrupted moves, automatic-scan recovery, manual-review reporting and temporary removal/restoration.

### Changed

- Share Windows Python/service-configuration discovery between the loudness and filename launchers, retaining separate-checkout support and explicit path overrides.
- Server source/package version is 0.8.0. Filename changes require running the maintenance command on the Windows PC; no service or Apple TV deployment is included.

## [0.7.1] - 2026-10-01

### Fixed

- Let the Windows loudness launcher reuse the Python executable recorded in the service's `background.json` when a separate source checkout has no local virtual environment. Continue loading scanner code from the invoking checkout.
- Add a `-PythonPath` override and actionable missing-environment errors without requiring a redundant library scan.

## [0.7.0] - 2026-10-01

### Added

- Resumable `mvideo measure-loudness` command and Windows launcher for first-audio-track EBU R128 measurements, including integrated loudness, true peak, loudness range and threshold, without modifying source media or creating conversions.
- Per-video SQLite checkpoints with source/profile invalidation, progress and coverage reporting, bounded batches, force remeasurement, timeouts, duplicate-run locking, and retryable errors. Silence/below-gate and missing-audio states are stored explicitly.
- Real FFmpeg and regression coverage for level differences, first-track selection, source preservation, cached/resumed runs, interruption, file changes, errors and locking.

### Changed

- Server source/package version is 0.7.0. Measurements prepare future normalization; Apple TV playback gain is not yet implemented and this release has not been deployed.

## [0.6.0] - 2026-10-01

### Added

- Double-tap the right edge of the Siri Remote touchpad during playback with controls hidden to skip to the next video, including normal end-of-selection behavior.
- Keep single-tap seeking and rightward navigation in playback controls and Up Next available.

## [0.5.0] - 2026-10-01

### Added

- Shared, ordered server playlists with authenticated create/read/update/delete, atomic saves, conflict detection, unavailable-video retention and complete ordered/shuffled queues.
- Apple TV Playlists navigation, cover thumbnails, descriptions, counts, refresh, continuous playback and restored focus.
- Browser Playlist studio on the existing private server: pairing, drag-and-drop, search/decade filters, accessible reorder controls, rename/remove/delete, unsaved-change protection and responsive layouts.
- Catalog-matched starters: Eurodance (37 videos), Glam metal & hard rock (42), and Chart toppers (24 verified UK Top 10 songs), with reproducible recipes and chart sources.
- Preview/apply CLI seeding that preserves later edits and deletions; packaged web assets requiring no Node.js on Windows.

### Changed

- Upgrade the Windows service and tvOS app to 0.5.0, build 4; deploy and populate the server, and deliver the Apple-processed build to the existing internal TestFlight group.

## [0.4.1] - 2026-10-01

### Fixed

- Resolve artist identities automatically from MusicBrainz song credits so fanart.tv photos are available beyond the three manually configured artists.
- Load artwork for visible artist tiles and artist pages in the background, replacing temporary video stills as photos arrive.
- Revisit negative cache entries from the manual-only lookup and preserve biographies when the artwork provider fails.
- Keep ambiguous or missing matches on the video fallback, with bounded requests, caching and manual identity overrides.

### Changed

- Deploy the Windows artwork correction and publish tvOS 0.4.1 (3) to the existing mvideo testers TestFlight group.

## [0.4.0] - 2026-10-01

### Added

- Image-backed artist, year and decade tiles with readable gradient overlays, scoped video stills and cached verified fanart.tv artist artwork.
- Remote-selectable artist photos with a full-screen viewer and return focus.

### Fixed

- Reserve video thumbnail layout bounds and separate the Artist photos section so it no longer overlaps the last video row.
- Make the artist photo row reachable with the Apple TV remote.

### Changed

- Display Artist - Track (Year) in native playback controls, with graceful handling of missing artist/year metadata.
- Bump the Windows service and tvOS app to 0.4.0, TestFlight build 2.
- Deploy the Windows update and publish tvOS 0.4.0 (2) to the existing mvideo testers TestFlight group.

## [0.3.0] - 2026-10-01

### Added

- Native tvOS app with Home, search, artist/year/decade pages, Keychain pairing and cinematic remote focus.
- Native AVKit playback with complete-scope queues, shuffle, next-item preparation, seeking, previous/next and up-next controls.
- Random fanart.tv home photography from verified artists in the real library, with artist credit and thumbnail fallback.
- Windows boot task running as Local Service without login, restricted ProgramData state, encrypted provider provisioning and automatic incremental scans.
- Dedicated app identity, branded tvOS assets, simulator tests and App Store distribution archive/export configuration.
- Real-library verification tooling for source preservation, representative conversions, seeking and aspect ratio.

### Fixed

- Preserve anamorphic display aspect ratio when transcoding and generating thumbnails.
- Restore the focused video and exact scroll offset after playback without reloading the page.
- Retain the catalog on partial directory walks and prevent overlapping scans across processes.
- Probe newly indexed videos asynchronously when playback starts before the scan completes.
- Combine artist capitalization variants and retain fanart.tv availability independently of biography provider failures.

### Changed

- Deployed private Windows HTTPS on port 8443 and indexed all 15,559 library videos.
- Published tvOS 0.3.0 (1) to the dedicated internal TestFlight group and sent the requested tester invitation.

## [0.2.0] - 2026-10-01

### Added

- Read-only Windows-capable library service with incremental SQLite/FTS5 indexing, pagination, scoped queues and conservative filename review.
- One-time pairing, hashed sessions, revocation and scoped expiring media access.
- FFprobe-driven direct/remux/transcode policy, bounded conversion cache and lazy thumbnails.
- Server-only Last.fm/fanart.tv metadata with explicit artist identity, attribution, caching and backoff.
- Windows diagnostics, foreground launcher and DPAPI provider setup; implementation plan and real SMB sample evidence.
- Critical service tests including a 15,000-video catalog.

### Changed

- Recorded design approval and replaced concept-only setup instructions with runnable service documentation.

## [0.1.0] - 2026-10-01

### Added

- Five Apple TV visual concepts: home, search, artist, year and decade.
- Design review notes and image-generation prompts for future revisions and Mac handoff.
- Project README documenting intended features, current concept-only status and planning steps after approval.
- Git exclusions for local environment credentials and OS metadata.
