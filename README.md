# mvideo

A native Apple TV music video app backed by an independent Windows library and streaming service. The five [approved designs](docs/design/README.md) guide the charcoal, warm-white and amber interface. The collection spans every era present in the files.

Implementation is underway. The first service milestone is runnable; native tvOS and TestFlight verification follow the [implementation plan](docs/implementation/PLAN.md). See [verification evidence](docs/implementation/VERIFICATION.md) for the distinction between local, Windows, simulator and physical-device results.

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

The proposed server binds `127.0.0.1:8765` by default. This is **new mvideo configuration**, not a discovered Windows endpoint. The Windows PC is reachable over Tailscale at `jorncomputer.tail5ef358.ts.net` / `100.105.78.85`. Existing port 443 serves another app and must remain untouched. Inspect `tailscale serve status` on Windows before selecting a separate HTTPS port. Keep access private to the tailnet; no Funnel/public exposure is required. The Apple TV must join the same tailnet.

### Windows

The source root defaults to `L:\MusicVideos`. Run these from the cloned repository in PowerShell:

```powershell
.\scripts\windows-diagnostics.ps1
.\scripts\windows-save-providers.ps1
.\scripts\windows-start.ps1 -Scan
.\scripts\windows-start.ps1
# In a second window:
.\scripts\windows-start.ps1 -Pair
```

`windows-start.ps1` installs the Python environment and runs the service in the foreground, bound to loopback. It is not yet a registered Windows Service. Keep that console running. State is `%LOCALAPPDATA%\mvideo` under the logged-in account, which must be able to access `L:`. Installing an unattended task/service and selecting its account requires Windows execution access and verification that its drive is visible.

The provider setup prompts without echo and stores Last.fm/fanart.tv keys using current-user Windows DPAPI. Run setup and service under the same Windows account. The local Mac `.env` is not transferred by Git. `LAST_FM_SECRET` is not required by the public biography method. Never copy keys into Swift sources or app resources.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `MVIDEO_LIBRARY` | `L:\MusicVideos` | Read-only source directory |
| `MVIDEO_STATE` | `.state` (Windows launcher uses LocalAppData) | Database and derived caches; must be outside source root |
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

Only approve an artist MusicBrainz UUID after checking the artist's identity. Name-only Last.fm results are candidates; the app must show metadata unavailable until identity is verified. Verified metadata is cached for 24 hours; failed/missing matches for 15 minutes. Requests are serialized at no more than one per second with rate-limit backoff. Artist pages carry Last.fm and fanart.tv credit/source links. No provider crawl is performed during scanning.

### Playback and queues

The server uses actual FFprobe stream metadata, not extensions. Conservative first-generation Apple TV 4K baseline: progressive H.264 up to 1080p/60, 8-bit 4:2:0 and AAC-LC stereo in MP4 plays directly. Compatible streams in other containers are remuxed; incompatible audio/video receives a cached H.264/AAC MP4 derivative. Interlaced material is deinterlaced; sample aspect ratio is preserved. HDR needs explicit compatibility review and is not silently converted to washed-out SDR.

Conversions run one at a time and must finish before playback, enabling full-file byte-range seeking. Initial conversion can take time, especially 4K VP9. Original files remain unchanged. Native playback will prefetch the next queue item. HLS/adaptive renditions are evaluated in the plan but are not currently implemented. Cache outputs are pinned while media tickets remain valid; old unpinned outputs are evicted. A full cache reports a recoverable conversion error.

A queue snapshots all matching IDs, not just the visible page. Shuffle is a permutation without repeats. Selecting a video starts there and wraps through the rest of the same scope once. At exhaustion the app can offer replay. Deleted/unavailable items produce explicit retry/skip behavior.

## Design and evidence

- [Implementation plan](docs/implementation/PLAN.md)
- [Verification and delivery gates](docs/implementation/VERIFICATION.md)
- [Approved images](docs/design/README.md) and [generation prompts](docs/design/PROMPTS.md)

Generated concept photography, counts and example biographies are reference material only and are never treated as real catalog/provider data.
