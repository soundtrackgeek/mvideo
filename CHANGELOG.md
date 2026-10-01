# Changelog

## [0.4.1] - 2026-10-01

### Fixed

- Resolve artist identities automatically from MusicBrainz song credits so fanart.tv photos are available beyond the three manually configured artists.
- Load artwork for visible artist tiles and artist pages in the background, replacing temporary video stills as photos arrive.
- Revisit negative cache entries from the manual-only lookup and preserve biographies when the artwork provider fails.
- Keep ambiguous or missing matches on the video fallback, with bounded requests, caching and manual identity overrides.

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
