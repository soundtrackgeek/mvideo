# mvideo: improvement and feature ideas

Reviewed on 2026-10-04 against **server 0.11.2**, **Apple TV app 0.11.1 (12)** and **Playlist studio 0.5.0**. This is a planning document; none of it is implemented. Library figures come from the README and [verification notes](implementation/VERIFICATION.md): 15,558 available videos, 513 needing a video transcode, 41 needing an audio transcode, 114 filename warnings, 28 unknown years and 17 failed loudness analyses.

**Effort:** **S** ≈ a day · **M** ≈ several days · **L** ≈ a week or more. **Impact** is a judgement of how much the change affects day-to-day use of the library.

## Short list

If only a handful of these get done, these give the most for the effort:

1. **Automate the "add videos" pipeline and refresh Apple TV live** (improvements 1–2). This removes the four-step admin PowerShell routine and the need to close and reopen the app.
2. **Pre-convert the ~554 non-direct videos and keep their frame rate** (improvements 4–5). This removes the "Preparing…" wait and the 30 fps judder.
3. **Home shelves, play history and favourites** (improvement 10, features 1–2). Home currently shows the same alphabetical grid on every launch.
4. **"Music television" channels with on-screen credits** (feature 4). This fits the app's tagline better than anything else on the list.
5. **AcoustID audio fingerprints** (improvement 11, features 10–11, Part 3). They give reliable artist identity, release years, duplicate detection and IDs that survive renames.

---

## Part 1: 20 existing features that can be improved

### 1. Adding new videos (index → measure → reload)

**Today:** Adding files takes four manual steps in admin PowerShell: scan, run the loudness launcher, check its status, then fully close and reopen the Apple TV app. The service scans every 30 minutes but never measures loudness, so new videos play un-normalized until someone remembers the command. Each scan also opens a new SQLite connection and runs two queries for every one of the ~15.5k files, even unchanged ones ([library.py:92](../server/mvideo/library.py#L92)).

**Improve by:**
- After a scan with `changed > 0`, queue loudness measurement for exactly those IDs in a low-priority background worker inside the service. It can reuse `LoudnessScanner`, measure one video at a time at below-normal priority, and respect the existing scan lock. Keep the CLI for bulk and `--force` runs.
- Add a file-system watcher (`watchdog`) so a file dropped into `L:\MusicVideos` is indexed within about a minute instead of up to 30. If `L:` is an SMB mount, use its `PollingObserver` or keep the periodic scan as the fallback.
- Before probing, wait until a file's size and mtime are unchanged across two checks, so a half-copied file is never probed.
- Load `id, size, mtime, available, probe_error` for the whole catalog into memory once per scan, and open write transactions only for files that changed.

**Effort:** M · **Impact:** High

### 2. Keeping Apple TV in sync with the library

**Today:** The catalog already has a `revision` counter, but the app reloads only after an error, a scope change, or (for playlists) a return from the background. The README tells you to fully close the app after adding videos. Artist tiles and pages poll every 2–3 seconds until artwork resolves ([FacetCard.swift:50](../apps/tvos/MVideo/FacetCard.swift#L50), [Browse.swift:142](../apps/tvos/MVideo/Browse.swift#L142)).

**Improve by:**
- Push changes with Server-Sent Events. The pinned FastAPI 0.135 already includes native `fastapi.sse.EventSourceResponse`. A simpler alternative is to poll `/api/status` when the app becomes active and every few minutes.
- When the revision changes, show a non-blocking "12 new videos · Refresh" pill and refresh the current page in place, keeping focus.
- Send an `artwork-ready` event for an artist so tiles stop polling.

**Effort:** S–M · **Impact:** High

### 3. Video identity that survives renames and moves

**Today:** A video's ID is `sha256(relative path)` ([library.py:83](../server/mvideo/library.py#L83)). Renaming or moving a file outside the `fix-filenames` tool creates a new video and orphans its playlist entries, loudness measurement and overrides. The README spends a whole section on JSON rename plans to work around this.

**Improve by:**
- Store a content key next to the path: size plus duration plus a hash of the first and last 4 MB. This is cheap to compute even over SMB.
- During a scan, if a "new" file's content key matches a file that just disappeared, migrate the ID automatically (reusing the migration code in `filenames.py`) and log the move.
- Optionally add a Chromaprint audio fingerprint for an even stronger match (see Part 3).
- Keep `fix-filenames` for planned bulk cleanups only.

**Effort:** M · **Impact:** High

### 4. Waiting for videos that need conversion

**Today:** Conversion runs on one worker and must finish before playback starts ([playback.py:56](../server/mvideo/playback.py#L56)). The app polls every 2 seconds for up to an hour, showing only "Preparing this video…" ([Playback.swift:114](../apps/tvos/MVideo/Playback.swift#L114)). A 4K VP9 video can take minutes. Finished conversions sit in a 20 GB cache that evicts the oldest files, so the same videos keep being converted again.

**Improve by:**
- **Pre-convert:** add an idle-time or nightly job that converts all ~554 non-direct videos ahead of time into a separate folder that is never evicted. Measure the total size first; at roughly 8 Mbit/s it should be a modest amount of disk space.
- **Progress:** run FFmpeg with `-progress pipe:1` and return a percentage and ETA from `/api/playback`, so the TV can show "Converting… 42%".
- **Hardware encoding:** if the PC has a suitable GPU, use `h264_nvenc`, `h264_qsv` or `h264_amf` (or the jellyfin-ffmpeg build), which is usually several times faster than `libx264 -preset fast`.
- **Queue prefetch:** prepare the next 2–3 non-direct items in a queue, not just the next one.
- **Longer term:** stream fragmented-MP4 HLS (`-f hls -hls_segment_type fmp4`) so playback starts after the first segment. The implementation plan already lists HLS as a later optimization.

**Effort:** M for pre-conversion and progress, L for HLS · **Impact:** High for older and unusual formats

### 5. Conversion quality (frame rate, 4K, HDR)

**Today:** The transcode filter chain ends in `fps=30` and caps output at 1080p ([playback.py:121](../server/mvideo/playback.py#L121)). `bwdif=send_frame` correctly turns 50i/60i into 50p/60p, and the next filter immediately drops it to 30 fps, which makes performances visibly judder. 4K VP9 sources are reduced to 1080p H.264. HDR sources are refused as `unsupported_hdr` and show an error screen ([playback.py:30](../server/mvideo/playback.py#L30)).

**Improve by:**
- Keep the source frame rate and only cap it above 60 fps.
- Apple's specifications for the first-generation Apple TV 4K list H.264/HEVC SDR up to 2160p60 (Main/Main 10), and HEVC HDR10 and Dolby Vision profile 5. Convert 4K sources to HEVC (`libx265` or `hevc_nvenc`, with `-tag:v hvc1`) at their native resolution. Widen the direct-play rule to cover HEVC in MP4/MOV, after testing on the physical Apple TV.
- For HDR, either pass HDR10 through as HEVC Main 10 or tone-map to SDR (`zscale` + `tonemap`, or jellyfin-ffmpeg's GPU tone-mapping) instead of refusing playback.
- Bump the cache key prefix (`v2-` → `v3-`) so the new rules regenerate existing conversions cleanly.

**Effort:** M · **Impact:** Medium–High (picture quality)

### 6. Thumbnails

**Today:** Each thumbnail is taken at 10% of the video's duration, capped at 10 seconds ([playback.py:161](../server/mvideo/playback.py#L161)). For almost every video that means second 10, which is often black, a title card or a label ident. Thumbnails are created only when first viewed, one at a time behind a global lock ([playback.py:156](../server/mvideo/playback.py#L156)), so a fresh 48-video grid is extracted one video at a time. There is a single 640 px size, which the home and artist hero stretches across most of a 4K screen.

**Improve by:**
- Pick a better frame: seek to about 20–35% and use FFmpeg's `thumbnail` filter, which chooses the most representative frame from a batch, together with `blackframe` to skip dark frames. PySceneDetect is an option for choosing a frame in the middle of a shot.
- Pre-generate thumbnails at idle priority after each scan. Remove the global lock; the two-worker pool already limits concurrency.
- Produce two sizes: about 480 px wide for grids and 1280 px for heroes.
- Add "Use current frame as thumbnail" in the player or studio, stored as an override.

**Effort:** S–M · **Impact:** Medium (the whole UI looks better)

### 7. Image loading and caching

**Today:**
- Every catalog response signs fresh image URLs whose ticket includes `now + 4h` ([auth.py:47](../server/mvideo/auth.py#L47)). The same thumbnail therefore gets a new URL on every load, and neither the client's URL cache nor `Cache-Control: max-age=3600` ever gets a hit.
- The app uses `AsyncImage`, which has only the small shared URL cache and decodes full-size images. fanart.tv backgrounds are full HD but shown as 270-point tiles.
- Artist image downloads are serialized behind one lock ([metadata.py:223](../server/mvideo/metadata.py#L223)).

**Improve by:**
- Round ticket expiry to fixed time buckets (for example, the end of the next 4-hour window) so a URL stays the same, and cacheable, for hours.
- Replace `AsyncImage` with Nuke's `LazyImage`, which supports tvOS. It provides a memory and disk cache, downsampling to the tile size, prefetching of the next page, request priorities and cancellation.
- Create resized versions of fanart on the server with Pillow (640, 1280 and 1920 px wide) and request the size that fits.

**Effort:** S for ticket buckets, M for Nuke and resized images · **Impact:** High (smoother scrolling, less Tailscale traffic)

### 8. Search

**Today:** Search is an FTS5 prefix match over artist, title and year ([library.py:142](../server/mvideo/library.py#L142)), entered in a plain `TextField` with a 350 ms debounce ([Browse.swift:319](../apps/tvos/MVideo/Browse.swift#L319)). Results are videos only. Spelling variants don't match each other ("Guns and Roses" / "Guns N' Roses", "Aha" / "a-ha"), and there are no suggestions or recent searches.

**Improve by:**
- Use SwiftUI `.searchable` with `searchSuggestions` on tvOS. This gives the system search layout, dictation, and artist suggestions from a new `/api/suggest` endpoint.
- Group results as **Artists**, then **Videos**, then **Playlists**, as in the original search concept image.
- Add a `tokenize='trigram'` FTS5 table as a fallback for substring and near-miss matches. Add normalization rules for `&`/`and`, `'n'`, punctuation and a leading "The".
- Remember the last 10 searches.

**Effort:** M · **Impact:** Medium–High

### 9. Browsing long lists (artists, years, decades)

**Today:** Artists load 60 at a time behind a **Load more** button ([api.py:195](../server/mvideo/api.py#L195), [Browse.swift:200](../apps/tvos/MVideo/Browse.swift#L200)). With thousands of artists, reaching "Z" takes dozens of presses. Year pages always show the three years either side, even when they have no videos ([Browse.swift:342](../apps/tvos/MVideo/Browse.swift#L342)). Decade pages show all ten years whether or not each has videos.

**Improve by:**
- Load the next page automatically when one of the last ~6 items appears on screen, in every grid.
- Add an A–Z / 0–9 jump rail on Artists. The server can return the starting offset of every initial letter in one grouped query.
- Add sorting by name, number of videos and recently added.
- Show year and decade chips with video counts, and skip empty years, using the existing `years` facet.

**Effort:** S–M · **Impact:** Medium–High

### 10. Home screen

**Today:** Home has a hero and a grid of the first 48 videos in alphabetical artist order ([Browse.swift:368](../apps/tvos/MVideo/Browse.swift#L368)), so every launch shows the same number-named and "A" artists. Only the hero background changes.

**Improve by:**
- Replace the grid with horizontal shelves, each backed by a small query:
  - Random picks, re-rolled on each launch
  - Recently added (this needs a new `added_at` column; the `videos` table has no timestamps)
  - Your playlists
  - "40 years ago: 1986"
  - A decade spotlight
  - The featured artist's videos
  - Once play history exists: Continue, Recently played, and Rediscover (not played for a year)
- Add a `/api/home` endpoint that returns every shelf in one request, so launch stays fast over Tailscale.

**Effort:** M · **Impact:** High

### 11. Artist matching and collaborations

**Today:** Matching is careful and conservative. Collaboration credits are skipped on purpose ([artist_match.py](../server/mvideo/artist_match.py)). As a result, filename artists such as "X feat. Y", "X & Y" or "X vs. Y" become separate artists with no photos and no link to X's page. Lookups happen only when an artist is browsed, and all providers share one global limit of one request per second ([metadata.py:73](../server/mvideo/metadata.py#L73)).

**Improve by:**
- Parse "feat.", "ft.", "featuring", "&", "and", "x", "vs." and "with" into an `artist_credits` table, so a video appears on every participant's page while keeping its display name.
- Give each provider its own rate limit. MusicBrainz needs one request per second, but fanart.tv and Last.fm can run alongside it, so artwork would arrive several times faster.
- Add an optional overnight crawl that matches every artist once, so all tiles end up with photos.
- Use AcoustID fingerprints for definitive recording → artist MBID matches (Part 3).

**Effort:** M · **Impact:** Medium–High

### 12. Artist pages

**Today:** The page shows two lines of the English Last.fm `bio.summary`, which is truncated at about 300 characters ([metadata.py:128](../server/mvideo/metadata.py#L128)), and up to 12 fanart.tv backgrounds plus one thumbnail. The fanart.tv response already contains `hdmusiclogo`, `musiclogo` and `musicbanner`, but they are thrown away ([metadata.py:158](../server/mvideo/metadata.py#L158)).

**Improve by:**
- Show the transparent HD logo in the hero instead of plain text. This costs no extra requests.
- Use `bio.content` (the full text) for the **Biography** sheet.
- Offer Norwegian biographies if wanted: Last.fm `artist.getInfo` accepts `lang=no`, and TheAudioDB has `strBiographyNO` (a-ha has one). Wikipedia's `page/summary`, found through Wikidata's MusicBrainz ID property P434, gives a cleaner lead paragraph.
- Add a facts row with origin, formation year and genre (from TheAudioDB or MusicBrainz), plus "Similar artists in your library" (feature 6).
- Add a chronological "career" order for the artist's videos, with a toggle back to A–Z.

**Effort:** S for logos, M for the rest · **Impact:** Medium

### 13. Metadata review (unknown years and filename warnings)

**Today:** 114 filename warnings and 28 unknown years can only be fixed with `mvideo override VIDEO_ID …` on the PC, followed by a rescan.

**Improve by:**
- Suggest years automatically from the MusicBrainz recording `first-release-date` (or an AcoustID match), labelled with how confident the match is.
- Add a review queue in the browser (feature 19) showing the filename, parsed fields, warnings and suggestions, with **Accept / Edit / Skip**. Saving writes the override and re-indexes just that video, with no rescan.
- Use the same queue for "ambiguous separator" names, where one quick human choice decides which part is the artist and which is the title.

**Effort:** M · **Impact:** Medium

### 14. Shuffle

**Today:** Shuffle is a uniform random permutation ([playback.py:11](../server/mvideo/playback.py#L11)). In a 15.5k library with prolific artists, the same artist often comes up twice within a few videos, and **Shuffle all** ignores whether you watched a video yesterday.

**Improve by:**
- Add **smart shuffle**: shuffle, then spread the order so an artist doesn't repeat within N videos. The starter playlists were interleaved this way by hand.
- Once history and ratings exist (features 1–2), optionally weight the order: favourites more often, recently played or disliked videos less often.
- Add variants such as "alternate decades" or "an artist's career in random order".
- Store the shuffle seed so a resumed session can recreate the same order.

**Effort:** S–M · **Impact:** Medium–High

### 15. Queue, Up Next and transitions

**Today:** Up Next loads 8 videos with 8 sequential `/api/videos/{id}` requests ([Playback.swift:221](../apps/tvos/MVideo/Playback.swift#L221)). You can't add to, remove from or reorder the queue. The next `AVPlayerItem` is only created after the current one ends, so each video starts with a request round-trip and a buffering gap.

**Improve by:**
- Add a batch endpoint (`POST /api/videos/batch`, up to ~50 IDs) and show 20+ upcoming videos.
- Add **Play next** and **Add to queue** to every video card. The queue lives in the app, so this is mostly UI work.
- Create the next item about 10 seconds before the current one ends (using `AVQueuePlayer` or a second preloaded item), with its normalization tap already attached, for near-gapless transitions.

**Effort:** M · **Impact:** Medium–High

### 16. Player information and controls

**Today:** Each player item gets only title and artist metadata ([Playback.swift:148](../apps/tvos/MVideo/Playback.swift#L148)). The AVKit info panel has no artwork, year, description or genre. All custom actions are inside the transport-bar menu.

**Improve by:**
- Add artwork (the thumbnail or artist fanart), a description (a biography snippet or video credits), the year and the genre to `externalMetadata`.
- Use AVKit's `contextualActions` (tvOS 15+) to show **Go to artist** or **Favourite** as a corner button during the first and last seconds of each video.
- Use `infoViewActions` to replace "Play from beginning" with mvideo's own actions.
- Add a sleep timer and **Stop after this video**.

**Effort:** S–M · **Impact:** Medium

### 17. Volume normalization

**Today:** The foundation is solid. The target is a fixed −18 LUFS, with a −2 dBTP source-peak ceiling and a +12 dB maximum boost. The only peak protection is a simple sample clamp, not a true-peak limiter. The only control is on or off. 17 videos failed analysis and play at their original volume, and new videos wait for a manual measurement run (see improvement 1).

**Improve by:**
- Add a setting for the target loudness (−14, −16, −18 or −20 LUFS). The gain calculation already takes these values as parameters.
- Add a small look-ahead limiter to the audio tap, so quiet tracks can get their full boost without clipping.
- Add an optional **Night mode** compressor for late-evening viewing.
- List the 17 failures with each file and its FFmpeg error. Retry them automatically by measuring a remuxed or decoded copy.
- Show the gain being applied (for example, "−4.2 dB") in Up Next.

**Effort:** M · **Impact:** Medium

### 18. Playlist studio editing

**Today:** The editor covers search, a decade filter, drag-and-drop, add, reorder, rename, description and delete, with version checks against conflicting edits. It has no durations or total runtime: the probe data includes duration, but the catalog response doesn't send it. There is also no bulk add, no way to duplicate a playlist, no sorting or interleaving tools and no cover choice. Apple TV can't edit playlists at all.

**Improve by:**
- Send `duration` (from `probe.format.duration`) and show it per row and as a playlist total.
- Add **Add all results** (with a cap and a confirmation), multi-select add and remove, **Duplicate playlist**, **Sort by year or artist**, **Interleave artists** and **Shuffle order once**.
- Add a paste import: paste `Artist - Title` lines (for example, a chart copied from Wikipedia) and match them with the normalizer the starter recipes already use, listing any lines that didn't match.
- Let the user choose the cover video, and export or import playlists as JSON or M3U.

**Effort:** M · **Impact:** Medium

### 19. Pairing, sessions and connection reliability

**Today:**
- Pairing an Apple TV means typing a full HTTPS address with the Siri Remote, plus an eight-digit code generated in PowerShell.
- Sessions expire after a fixed 90 days and are never extended ([auth.py:34](../server/mvideo/auth.py#L34)), so the TV falls back to the pairing screen about every three months.
- Media and image links are signed with a key created when the server process starts ([auth.py:15](../server/mvideo/auth.py#L15)). Any service restart or update invalidates every link in use, and a playing video fails at its next range request.

**Improve by:**
- Prefill the last-used address and the known tailnet name. Accept a bare host name and add `https://` and `:8443` automatically.
- Add **Pair a new device** to Playlist studio, which creates a code from an already paired browser, so pairing no longer needs PowerShell.
- Extend a session whenever it is used (for example, renew when fewer than 30 days remain).
- Store the signing key in the protected state directory (DPAPI-encrypted on Windows) so links survive restarts. When a media link returns 401, the app should request playback again and resume at the same position.
- Expand the Connection sheet to show server version, latency, scan status and the most recent error.

**Effort:** S–M · **Impact:** Medium–High

### 20. Service operations, backups and the release pipeline

**Today:**
- Backups are only made by hand or by `fix-filenames`.
- Nothing alerts you when the PC, the service or Tailscale is down, and logs only exist on the PC.
- Xcode Cloud archives and uploads a TestFlight build on every push to `master`, including documentation-only and server-only commits, unless the commit message contains `ci skip`.
- Server tests don't run in CI, and Windows-only code paths (`msvcrt` locking, the PowerShell launchers) are only tested by hand.

**Improve by:**
- Make a nightly online SQLite backup with Python's `Connection.backup`, keeping 7 daily, 4 weekly and 6 monthly copies, and copy them off the PC (OneDrive, a NAS, or rclone to object storage).
- Ping Healthchecks.io after each scan and backup, monitor `/health` from outside the PC, and send alerts to your phone with ntfy or Pushover.
- Give the Xcode Cloud workflow a start condition limited to `apps/tvos/**`. This saves compute hours and avoids empty TestFlight builds.
- Add GitHub Actions jobs: `pytest` on `windows-latest` and `ubuntu-latest`, `npm test` and a build for the studio, and `ruff` linting.

**Effort:** S–M · **Impact:** Medium (peace of mind)

---

## Part 2: 20 new features worth adding

### 1. Play history and resume

**What:**
- Record every play on the server: video, start time, seconds watched, whether it finished or was skipped, and where it was started from.
- Use that record for Recently played, Most played, Never played and Rediscover.
- Add **Resume**: reopening the app continues the last queue at the same video and position.

**How:**
- The app sends start, progress and end events in batches, without waiting for a reply.
- A queue snapshot (IDs, position and shuffle seed) is stored on the server for each device.
- New filters such as `never_played` and `played_since` are added to `Library.scope()`.

**Effort:** M · Features 2, 3, 14, 16 and 17 build on this.

### 2. Favourites, ratings, hiding, and adding to playlists from the TV

**What:**
- Thumbs up, thumbs down and **Never play again**, available from the player (menu or contextual action) and from a long-press on any card.
- An **Add to playlist…** sheet that lists your playlists.

**How:**
- Store ratings in a `ratings` table, and leave hidden videos out of shuffles by default.
- Add an append endpoint (`POST /api/playlists/{id}/items`) so adding one video from the TV never conflicts with an edit open in the browser.

**Effort:** S–M

### 3. Smart playlists

**What:** Playlists defined by rules that update automatically. Examples: "1980s favourites", "never played, 1990–1994", "added in the last 30 days", "videos from 30 years ago".

**How:**
- Store the rules as JSON on the playlist (`kind: smart`) and translate them into the existing `Library.scope()` query.
- The studio gets a rule builder.
- The Apple TV plays smart playlists like any other playlist.

**Effort:** M

### 4. "Music television" channels with on-screen credits

**What:**
- The app's tagline is "Your own music television." Add lean-back channels that start instantly and never run out: 80s, 90s, Eurodance, Hard rock, Deep cuts, Your favourites.
- At the start and end of each video, show MTV-style lower-third credits: Artist, "Title", Album or Year, Director.
- Optionally, show a three-second "Up next" card between videos using the next artist's fanart and logo.

**How:**
- A channel is a smart playlist with smart shuffle and endless refill.
- Draw the overlay in `AVPlayerViewController.contentOverlayView`, timed by player time observers (about 0:04–0:12 and the last 15 seconds).
- Credits come from IMVDb and MusicBrainz (feature 11).

**Effort:** M–L · This is the feature that best fits the product's identity.

### 5. Genres and moods

**What:** Browse and shuffle by genre or style (Synthpop, Eurodance, Hair metal, New wave, Hip hop…) and by mood. The catalog has no genre data today, so every themed playlist has to be made by hand.

**How:**
- Collect artist-level tags from Last.fm `artist.getTopTags`, MusicBrainz genres and TheAudioDB `strGenre` / `strStyle` / `strMood`.
- Map them onto a curated list of about 30 genres to filter out noisy tags, and store the result in `video_genres`.
- Audio-based classification with Essentia is possible as an offline batch job, but its TensorFlow builds only run on Linux (see Part 3).

**Effort:** M

### 6. Similar artists and artist radio

**What:**
- A "Fans also like" row on artist pages, showing only artists that are in your library.
- A **Start artist radio** button that plays the artist plus similar artists, smart-shuffled.

**How:**
- Cache Last.fm `artist.getSimilar` results (queried by MBID; each result has a match score) for each artist.
- Keep only the artists in your library.
- The radio is a queue built from that weighted set of artists.

**Effort:** S–M

### 7. Synced lyrics and karaoke mode

**What:** A lyrics option in the player that shows line-by-line synced captions over the video, or a karaoke-style side panel.

**How:**
- LRCLIB's `/api/get` (free, no key) returns LRC-timed lyrics by artist, title and duration. Cache them on the server and display them using a player time observer.
- Video edits often differ from album versions, so add a ±offset adjustment, and hide lyrics when the durations differ by more than a few seconds.

**Effort:** M

### 8. Intro and outro trimming

**What:** Many music videos have long silent intros, label idents, black frames or spoken skits. Optionally start each video where the music starts and stop where it ends.

**How:**
- The loudness pass already decodes the audio. Add `silencedetect` to it, plus a quick `blackdetect` on the video, and store suggested start and end times.
- The player seeks to the start time and sets `forwardPlaybackEndTime` to the end time.
- Add per-video in and out points in the studio.
- Setting: **Off / Silence only / Silence and black**.

**Effort:** M

### 9. Black-bar auto-crop ("zoom to fill")

**What:** Many 80s and 90s videos have letterboxing inside a 4:3 frame, or black bars on all four sides from earlier conversions. On a 16:9 TV they appear as a small rectangle in the middle of the screen.

**How:**
- Run FFmpeg `cropdetect` once per video and store the crop rectangle.
- Either scale the player view up and clip it in the app, or apply the crop during conversion on the server.
- Offer **Auto crop** as a setting, with an off switch for individual videos.

**Effort:** M

### 10. Duplicate and alternate-version finder

**What:** A report listing exact duplicates, alternate versions (live, extended, censored, remastered) and lower-quality copies, with a suggestion of which file to keep. The starter-playlist seeding already reports some alternate versions.

**How:**
- Group videos by normalized artist and title.
- Confirm matches with Chromaprint audio fingerprints and FFmpeg's `signature` filter (an MPEG-7 video fingerprint).
- Compare resolution and bitrate from the probe data.
- The report is read-only; deleting stays a manual decision.

**Effort:** M

### 11. Video credits and "behind the video"

**What:**
- An information page for each video: director, production company, release date, original album, label, chart peak and a short description.
- Browsing by director (Spike Jonze, David Fincher, Anton Corbijn…).

**How:**
- Match videos by artist and title against IMVDb, a music-video database with director and crew credits and a free API key.
- Get album, label and first release date from MusicBrainz recordings and releases, and chart positions from Wikidata where available.
- Cache the results in a `video_details` table.

**Effort:** M

### 12. Chart collections and "On this day"

**What:** Automatically built collections such as "UK number ones of 1985 in your library" or "US Top 10, 1991", and a Home shelf of videos released on today's date.

**How:**
- There is no free official UK or US chart API. Sources are Wikidata's `charted in` property (P2291) with ranking qualifiers (incomplete coverage), Wikipedia chart tables, or more curated recipes like `starter-playlists.json`.
- "On this day" needs full release dates. MusicBrainz `first-release-date` has month and day for many singles.

**Effort:** M (getting reliable data is the hard part)

### 13. Wishlist of missing hits

**What:** On each artist page, a "Popular songs you don't have" list as a collector's checklist.

**How:**
- Compare Last.fm `artist.getTopTracks` (or IMVDb's list of the artist's videos) against your normalized titles.
- Let the user mark a song as "no video exists".
- The list is for reference only; nothing is downloaded.

**Effort:** S–M

### 14. Top Shelf extension

**What:** When mvideo is in the top row of the Apple TV Home Screen, show your playlists, channels and Continue items above it. Selecting one goes straight into playback.

**How:**
- A `TVTopShelfContentProvider` extension using sectioned content.
- It shares the Keychain session with the app through an app group.
- Deep links such as `mvideo://playlist/{id}` open the selected item.
- It builds on `/api/home` (improvement 10) and play history (feature 1).

**Effort:** M

### 15. Phone remote and party requests

**What:**
- A **Now playing** page in Playlist studio for controlling the TV from your phone: see the current video, pause, skip and add to the queue.
- **Party mode:** the TV shows a QR code, and guests use it to search the library and add requests to the queue.

**How:**
- The app reports its playback state to the server and receives commands over Server-Sent Events, which FastAPI 0.135 supports natively.
- Guests get a short-lived token that only allows searching and adding to the queue.

**Effort:** L

### 16. Scrobbling to Last.fm and ListenBrainz

**What:** Record watched videos on your Last.fm and/or ListenBrainz profile.

**How:**
- The server submits plays from the history events in feature 1.
- ListenBrainz only needs a user token and `POST /1/submit-listens`.
- Last.fm's `track.updateNowPlaying` and `track.scrobble` require the shared secret and a one-time desktop authorization.
- Submit a play only after half the video or 4 minutes has been watched, whichever comes first, as ListenBrainz requires.

**Effort:** S–M

### 17. Statistics and year in review

**What:**
- **Your library in numbers:** videos per decade and per year, top artists by video count, total runtime, format mix and loudness spread.
- With play history, a December **mvideo Wrapped**: most-watched artists and decades, longest viewing streak.

**How:** One `/api/stats` endpoint, with a charts page in the studio and a simple tvOS screen.

**Effort:** S–M

### 18. Animated previews on focus

**What:** When a video card has been focused for about a second, a muted 4–6 second loop plays inside the tile, as in the Apple TV app.

**How:**
- Pre-generate short, low-bitrate clips in the background, for example `-ss <30%> -t 5 -an -vf scale=480:-2`.
- The tile plays its clip with an `AVPlayerLayer` and `AVPlayerLooper`.
- Previews can be turned off for slow connections.

**Effort:** M

### 19. Library admin dashboard in the browser

**What:** Turn Playlist studio into a control room:
- Scan now and scan status
- Loudness coverage and the 17 failures
- Conversion queue and cache use
- The filename-warning and unknown-year review queue (improvement 13)
- Artist identity fixes with MusicBrainz search
- Metadata overrides
- Pairing new devices and revoking sessions
- Service version, health and recent logs

**How:**
- Add `/api/admin/*` endpoints, optionally limited to sessions marked as admin.
- Add React pages next to the playlist editor. Each part can ship on its own.
- Together they remove most reasons to open admin PowerShell.

**Effort:** L, delivered in increments

### 20. iPhone, iPad and Mac app

**What:** Watch mvideo on other Apple devices, and use the iPhone as both playlist editor and remote.

**How:**
- The API client, models, `PlayerModel` and the normalization audio tap are not tvOS-specific, so they can be reused. Add iOS and macOS targets with touch and pointer layouts.
- Watching over Tailscale on mobile data needs adaptive bitrate (the HLS work in improvement 4). Downloads could add offline viewing.

**Effort:** L

---

## Part 3: Online services, APIs and libraries

### Metadata and artwork

| Service | What it adds to mvideo | Access and limits | Notes |
| --- | --- | --- | --- |
| **fanart.tv** (already used) | HD transparent logos (`hdmusiclogo`), `musiclogo` and `musicbanner`, in the response mvideo already fetches | Existing project key | Free improvement: stop discarding these fields (improvement 12) |
| **TheAudioDB** | Biographies in many languages, including Norwegian (`strBiographyNO`); logo, cutout, clearart, wide thumbnail, banner and fanart; genre, style and mood; formed year and country; a list of each artist's music videos by MusicBrainz ID (`mvid-mb.php`) | Free test key `123` at 30 requests/min; premium $8/month at 100/min | Looks artists up by MusicBrainz ID (`artist-mb.php`), which mvideo already resolves |
| **IMVDb** | Music-video data: director and crew credits, production companies, release year, YouTube/Vimeo IDs, stills | Free API key with an account | About 97k videos. The best source for "Directed by" (features 4 and 11) |
| **MusicBrainz** (already used) | Genres and tags, recording `first-release-date`, releases (album and label), band members, collaborations, aliases | 1 request/second, a User-Agent is required | Give it its own rate limiter (improvement 11) |
| **Cover Art Archive** | Single and album front covers by release group | Free (MusicBrainz and the Internet Archive) | Fallback artwork and artwork for the player info panel |
| **Wikipedia REST + Wikidata** | Fuller biographies (`/page/summary`) in many languages; structured facts; P434 links Wikidata to MusicBrainz IDs; `charted in` (P2291) chart positions | Free; send a descriptive User-Agent | Chart coverage is incomplete (feature 12) |
| **Last.fm** (already used) | Full bios via `bio.content` and `lang=no`; `artist.getSimilar`, `artist.getTopTags`, `artist.getTopTracks`; scrobbling | Existing key; scrobbling also needs the shared secret and a user session | Features 5, 6, 13 and 16 |
| **Discogs** | Fine-grained styles, labels, release years, credits | 60 requests/min authenticated, 25 unauthenticated | Accurate genre data for 80s and 90s releases |

### Identification, analysis and media processing

| Tool | What it adds | Access and limits | Notes |
| --- | --- | --- | --- |
| **AcoustID + Chromaprint** (`fpcalc`, `pyacoustid`) | Audio fingerprint → MusicBrainz recording: reliable artist identity, release dates for unknown years, duplicate detection, IDs that survive renames | Free for non-commercial use with an application key; `pyacoustid` limits itself to 3 requests/s | Can run in the same background pass as loudness measurement |
| **FFmpeg filters** (already installed) | `thumbnail`, `blackframe`/`blackdetect`, `silencedetect`, `cropdetect`, `signature` (MPEG-7 video fingerprint), `-progress`, HLS muxer with fMP4 segments, `zscale`/`tonemap` | Already installed | Covers improvements 4–6 and features 8–10 with no new dependencies |
| **jellyfin-ffmpeg** | Portable Windows FFmpeg build with tested NVENC/QSV hardware encoding and GPU HDR-to-SDR tone-mapping | Free | Swap it in with `MVIDEO_FFMPEG` / `MVIDEO_FFPROBE` |
| **PySceneDetect** | Shot detection for choosing thumbnails and preview clips | Free (BSD) | Optional; FFmpeg's `thumbnail` filter may be enough |
| **Essentia** (MTG, UPF) | Genre classification from audio (400 Discogs styles), mood, danceability, tempo | Free; AGPL code, models for non-commercial use | TensorFlow builds are Linux-only. Run as an offline batch on a Mac or Linux machine, not in the Windows service |
| **LRCLIB** | Synced (LRC) lyrics | Free, no key | Feature 7 |
| **ListenBrainz** | Scrobbling with a simple user token; listening history | Free | Simpler than Last.fm scrobbling (feature 16) |

### Apple platform APIs and Swift libraries

| API / library | What it adds | Notes |
| --- | --- | --- |
| **Nuke / NukeUI** (`LazyImage`) | Memory and disk image cache, downsampling, prefetching, request priorities; supports tvOS | MIT licence. Replaces `AsyncImage` (improvement 7) |
| **AVKit:** `contextualActions`, `infoViewActions`, `contentOverlayView`, `externalMetadata` | On-screen action buttons during playback, custom info-panel actions, lower-third overlays, artwork and description in the info panel | Built in (tvOS 15+). Improvement 16, feature 4 |
| **`AVQueuePlayer`** or preloaded items | Near-gapless transitions between videos | Improvement 15 |
| **TVServices** `TVTopShelfContentProvider` | Top Shelf carousel or sectioned content | Feature 14 |
| **SwiftUI `.searchable`** with `searchSuggestions` | Native tvOS search screen with suggestions and dictation | Improvement 8 |
| **swift-openapi-generator** + URLSession transport | Generates the Swift API client from FastAPI's OpenAPI schema. Export the schema at build time and keep `/openapi.json` disabled in production | Apache 2.0; transport supports tvOS 13+. Keeps app and server models from drifting apart |
| **Sentry** (Cocoa and Python SDKs) | Crash and error reports from the Apple TV and the service, with release health | Supports tvOS. Has a free single-developer plan; check current quotas. TestFlight crash logs exist but are slower to work with |

### Server, Windows and operations

| Tool | What it adds | Notes |
| --- | --- | --- |
| **FastAPI native SSE** (`fastapi.sse`, 0.135+) | Push library changes, artwork-ready events and remote-control commands | Already included in the pinned version. Improvement 2, feature 15 |
| **watchdog** | Index new files immediately (uses ReadDirectoryChangesW on Windows) | Use `PollingObserver` on SMB shares. Improvement 1 |
| **Pillow** (or pyvips) | Resize fanart and thumbnails to tile and hero sizes | Improvement 7 |
| **uv** | Fast, reproducible Python environments with a lockfile | Optional; would simplify `windows-update-service.ps1` |
| **Servy** | Runs the service as a native Windows service with health checks, restart policies, log rotation and a GUI | Alternative to the Task Scheduler launcher. NSSM and WinSW are no longer actively developed |
| **Healthchecks.io + ntfy** | Alerts when an expected scan or backup ping doesn't arrive; push notifications to your phone | Free tiers. Improvement 20 |
| **Uptime Kuma** | Self-hosted uptime monitor for `/health` over the tailnet | Alternative for HTTP checks |
| **GitHub Actions** + **Xcode Cloud file conditions** | Server and studio tests on Windows and Linux for every push; tvOS builds only when `apps/tvos` changes | Improvement 20 |

### Considered, but not recommended now

- **Spotify Web API for importing playlists:** Development Mode changed in February–March 2026. The app owner must have Premium, apps are limited to five users, and several groups of endpoints were removed. Recommendations and audio features have been unavailable to new apps since November 2024. Paste import (improvement 18) is simpler and won't break.
- **Litestream:** Windows isn't an officially supported platform. Scheduled SQLite online backups (improvement 20) are enough for this PC.
- **Official Charts and Billboard data:** there is no free official API, and scraping services carry terms-of-use risk. Use curated recipes and Wikidata instead.
- **AcousticBrainz:** shut down in 2022. Run Essentia locally if audio-based tags are wanted.
- **AI upscaling of SD videos** (Real-ESRGAN, Topaz and similar): the compute cost across 15k videos is very high, and the Apple TV already upscales. Reconsider only for a small set of favourites.

---

## Suggested order

1. **Quick wins (S):**
   - Stable image-link buckets
   - fanart.tv logos
   - Full Last.fm biographies
   - Keeping the source frame rate in conversions
   - A signing key that survives restarts
   - Sessions that renew when used
   - Xcode Cloud file filter
   - Batch Up Next endpoint
   - Automatic loading on scroll
2. **Foundations (M):**
   - Automatic loudness measurement and file watching
   - Live Apple TV refresh over Server-Sent Events
   - Pre-converting non-direct videos
   - Nuke image loading
   - Play history and favourites
   - Home shelves
3. **Signature features:**
   - Smart shuffle and smart playlists
   - Music-television channels with lower-third credits
   - Admin dashboard
   - AcoustID identity
4. **Expansion:**
   - Genres
   - Lyrics
   - Top Shelf
   - Phone remote and party mode
   - iPhone/iPad/Mac app

## Sources

- Apple: [Apple TV 4K (1st generation) technical specifications](https://support.apple.com/en-us/111929) · [AVPlayerViewController](https://developer.apple.com/documentation/avkit/avplayerviewcontroller) · [WWDC21: What's new in AVKit (contextual actions)](https://developer.apple.com/videos/play/wwdc2021/10191/) · [TVTopShelfContentProvider](https://developer.apple.com/documentation/tvservices/tvtopshelfcontentprovider) · [Xcode Cloud start conditions](https://developer.apple.com/documentation/xcode/configuring-start-conditions)
- Metadata: [fanart.tv image types (Music Assistant docs)](https://www.music-assistant.io/metadata/artwork/) · [TheAudioDB API](https://www.theaudiodb.com/free_music_api) · [IMVDb API](https://imvdb.com/developers/api/videos) · [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) · [Cover Art Archive API](https://mb.videolan.org/doc/Cover_Art) · [Last.fm artist.getInfo](https://www.last.fm/api/show/artist.getInfo) · [Discogs API rate limits (package docs)](https://www.nuget.org/packages/ParkSquare.Discogs) · [Wikidata `charted in` (P2291) usage](https://takco.readthedocs.io/en/latest/tutorials/chartedIn.html)
- Identification and analysis: [pyacoustid / AcoustID](https://pypi.org/project/pyacoustid) · [FFmpeg signature filter](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2017-March/105334.html) · [PySceneDetect](https://www.scenedetect.com/docs/0.6.3/cli.html) · [Essentia TensorFlow models](https://essentia.upf.edu/tutorial_tensorflow_auto-tagging_classification_embeddings.html) · [jellyfin-ffmpeg hardware acceleration](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration)
- Lyrics and scrobbling: [LRCLIB](https://lrclibapi.readthedocs.io/en/latest/examples/fetch_lyrics.html) · [ListenBrainz API](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html)
- Libraries and tooling: [Nuke](https://swiftpackageregistry.com/kean/Nuke) · [swift-openapi-generator](https://github.com/apple/swift-openapi-generator) · [swift-openapi-urlsession](https://swiftpackageregistry.com/apple/swift-openapi-urlsession) · [Sentry for tvOS](https://sentry.io/for/tvos/) · [FastAPI Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/) · [watchdog](https://pypi.org/project/watchdog/) · [Servy vs NSSM vs WinSW](https://dev.to/aelassas/why-i-built-servy-a-modern-open-source-alternative-to-nssmwinsw-kbm) · [ntfy + Healthchecks.io](https://themenonlab.blog/blog/ntfy-free-push-notifications)
- Caveats: [Spotify February 2026 Development Mode changes](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) · [Litestream v0.5 release notes](https://newreleases.io/project/github/benbjohnson/litestream/release/v0.5.3-beta1)
