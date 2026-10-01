# Verification — 2026-10-01

## Real library access

SMB is already mounted at `/Volumes/100.105.78.85` from `//jtillnes@100.105.78.85/L`. Read-only enumeration found **15,559 videos**: 15,065 MP4, 301 WebM, 182 MPG, 7 AVI, 2 MKV, 1 VOB, 1 WMV. Three non-video bookkeeping files are ignored.

Sixteen real files were probed without changing them: three MP4 (H.264/AAC), three MPG (MPEG-1/2 + MP2), three WebM (4K VP9/Opus), three AVI (MPEG-4 ASP/MP3), two MKV (VP9/AAC), one interlaced PAL VOB (MPEG-2/AC-3) and one WMV (WMV2/WMAv2). These results establish the need for transcoding; the extension alone is insufficient. Machine-local probe details are in ignored `output/codec-samples.json`. They are samples, not a complete codec census.

SMB read access does not establish Windows process/service control. SSH was rejected for `jtillnes` and `MicrosoftAccount\jtillnes@yahoo.com`. Windows service installation, existing Serve configuration, hardware transcoding availability and actual HTTPS port remain pending Windows execution access.

## Service verification

Initial suite: 16 passing tests covering conservative parsing, Unicode/punctuation search, incremental/offline/deleted scans, 15,000-row pagination, 15,001-item shuffle, scope intersection, revision conflict, one-time pairing/lockout/revocation, authenticated media byte-range/suffix/HEAD/416 requests, traversal prevention and codec policy. Run command: `.venv/bin/pytest server/tests -q`.

No claim yet of physical Apple TV playback, Windows service operation, archive upload or TestFlight availability.

## Reference and provider decisions

Tonehavn runs its server on loopback port 3210 behind HTTPS. Its iOS client validates an origin-only HTTPS URL, uses native URLSession/AVPlayer, and keeps account secrets out of UserDefaults. mvideo follows this separation with its own loopback service, explicit HTTPS origin and Keychain namespace. No Tonehavn source/configuration was modified.

Sources checked 2026-10-01:
- [Apple TV 4K first-generation specifications](https://support.apple.com/en-tm/111929). Owner believes this is the target model; tvOS version and device playback still unverified.
- [Apple HLS authoring specification](https://developer.apple.com/documentation/http-live-streaming/hls-authoring-specification-for-apple-devices/).
- [FFmpeg format documentation](https://ffmpeg.org/ffmpeg-formats.html). Completed MP4 VOD selected initially for reliable seek coverage; HLS remains a future optimization.
- [Last.fm artist.getInfo](https://www.last.fm/api/show/artist.getInfo): public API key required, user authentication/shared secret unnecessary, MusicBrainz UUID supported, error 29 is rate limiting.
- [Last.fm API terms](https://www.last.fm/api/tos): attribution and links retained. Personal use only in this milestone; broader/commercial distribution requires revisiting provider terms.
- [Official fanart.tv API client](https://github.com/fanart-tv/fanart.tv-api): music uses MusicBrainz artist IDs; project key required, personal client key optional, 429 backoff. Conservative one-request/second local budget is an application policy, not a claimed published quota.

## Release gates

| Gate | Status |
| --- | --- |
| Read actual Windows media | Verified through existing SMB mount |
| Install/start Windows service | Pending execution access |
| Real-library full codec census | In progress |
| tvOS simulator build/navigation/playback | Pending |
| Physical Apple TV | Not paired; unverified |
| mvideo signing/archive | Pending |
| Dedicated App Store Connect app | Not yet verified |
| Upload | Not attempted |
| Processing | Not started |
| TestFlight tester availability | Not available |
