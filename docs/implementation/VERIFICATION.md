# Verification — 2026-10-01

## Installed Windows service

The independent mvideo 0.4.0 service is installed at `L:\mvideo-service`, reads `L:\MusicVideos`, and stores runtime data under `C:\ProgramData\mvideo`. Python 3.13 and `C:\ffmpeg\bin` are used. Deployed Python source matches this repository.

The **mvideo Library** scheduled task is running as Local Service (`S-1-5-19`) with an `MSFT_TaskBootTrigger`, 30-second startup delay, failure restart and no execution time limit. It requires no interactive login. State/code ACLs and encrypted machine-DPAPI provider loading were installed with owner-approved administrator access. A fresh task launch and HTTPS health response passed. An actual Windows reboot was not performed. Tailscale's Windows service is Automatic.

Private HTTPS `https://jorncomputer.tail5ef358.ts.net:8443` forwards to `127.0.0.1:8765`. Tonehavn's port 443 route remains unchanged. No Funnel/public access was enabled. The native simulator paired over this HTTPS route and saved its session in the separate mvideo Keychain namespace.

## Real library and media verification

Full Windows scan: **15,559 indexed and probed videos**, zero pending/inaccessible files. Extension counts: 15,065 MP4, 301 WebM, 182 MPG, 7 AVI, 2 MKV, 1 VOB, 1 WMV. Codec policy classifies 15,005 direct, 513 video transcode and 41 audio transcode. There are 114 conservative filename-review warnings and 28 unknown years. These are metadata review states, not missing videos.

Sixteen initial real-file probes identified H.264/AAC, MPEG-1/2 + MP2, 4K VP9/Opus, MPEG-4 ASP/MP3, VP9/AAC, interlaced PAL MPEG-2/AC-3 and WMV2/WMAv2. Actual codecs establish the playback mode; extension alone is insufficient.

One real file from **each of the seven formats** subsequently passed Windows HTTPS playback preparation, initial/suffix byte ranges, FFprobe validation and FFmpeg decoding at the start, midpoint and near the end. MP4 played directly; the six other sampled formats used Windows-generated H.264/AAC derivatives. Source size and modification time remained unchanged. The verification session was revoked afterwards. Separately, local real-media conversions checked display aspect ratio, and generated integration fixtures verified remux, audio conversion, anamorphic transcoding, thumbnails and source preservation.

A Windows shuffle queue returned **15,559 unique IDs**, covering the entire selection. Machine-local evidence is in ignored `output/windows-verification.json`, `output/codec-samples.json` and `output/media-verification/results.json`. These are representative decode checks, not a claim that every video was played end to end. Audio tracks and audio decoding were verified; physical speaker output/listening remains unverified.

## Providers and home artwork

Verified library identities were installed for a-ha, Duran Duran and Tears for Fears. Each returned a real Last.fm biography and fanart.tv images over authenticated HTTPS; image fetches returned HTTP 200. Twelve featured-image requests sampled all three artists. The native home screen visibly rendered a Tears for Fears background, artist attribution and real catalog thumbnails, with 15,559 videos shown.

Home chooses a random available background from verified library artists once per launch, retains it during navigation and falls back to a library thumbnail. Additional artists need explicit MusicBrainz identity approval before provider content is displayed; the whole artist library has not been identity-matched. Provider credentials remain server-only, encrypted on Windows, and were not bundled in the app.

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

## TestFlight delivery

Dedicated app **mvideo - music videos**, App Store Connect ID **6818073365**, bundle **com.soundtrackgeek.mvideo**. The plain name mvideo was unavailable. No existing app identity was reused.

Version **0.3.0 (1)** uploaded successfully, completed Apple processing, and is **Testing** in the internal **mvideo testers** group. The requested account **jtillnes2@yahoo.com** already belonged to this Apple team and was added as a tester without changing its account permissions. App Store Connect visibly shows **Invited — Oct 1, 2026**, with one tester and one build. The owner subsequently confirmed installation, pairing and working playback on the physical Apple TV, and supplied photos of its browsing and player UI.

Local distribution artifacts: ignored `output/MVideo-0.3.0.xcarchive` and `output/export-0.3.0/MVideo.ipa`. [App Store Connect](https://appstoreconnect.apple.com/apps/6818073365/testflight/tvos).

## Reference and provider decisions

Tonehavn runs its server on loopback port 3210 behind HTTPS. Its iOS client validates an origin-only HTTPS URL, uses native URLSession/AVPlayer, and keeps account secrets out of UserDefaults. mvideo follows this separation with its own loopback service, explicit HTTPS origin and Keychain namespace. No Tonehavn source/configuration was modified.

Sources checked 2026-10-01:
- [Apple TV 4K first-generation specifications](https://support.apple.com/en-tm/111929). Owner believes this is the target model; exact model and tvOS version remain unverified; basic device playback is owner-confirmed.
- [Apple HLS authoring specification](https://developer.apple.com/documentation/http-live-streaming/hls-authoring-specification-for-apple-devices/).
- [FFmpeg format documentation](https://ffmpeg.org/ffmpeg-formats.html). Completed MP4 VOD selected initially for reliable seek coverage; HLS remains a future optimization.
- [Last.fm artist.getInfo](https://www.last.fm/api/show/artist.getInfo): public API key required, user authentication/shared secret unnecessary, MusicBrainz UUID supported, error 29 is rate limiting.
- [Last.fm API terms](https://www.last.fm/api/tos): attribution and links retained. Personal use only in this milestone; broader/commercial distribution requires revisiting provider terms.
- [Official fanart.tv API client](https://github.com/fanart-tv/fanart.tv-api): music uses MusicBrainz artist IDs; project key required, personal client key optional, 429 backoff. Conservative one-request/second local budget is an application policy, not a claimed published quota.

## Release gates

| Gate | Status |
| --- | --- |
| Full real Windows catalog/probes | 15,559 complete; zero pending/inaccessible |
| Boot service configuration and fresh task launch | Verified Local Service, no login; actual reboot untested |
| Private HTTPS and pairing | Verified Windows route and native Keychain |
| Representative seven-format playback and seeking | Passed through Windows HTTPS; originals unchanged |
| Live Last.fm/fanart.tv and random home image | Verified for three approved artist identities |
| tvOS simulator build/navigation/playback | Eight tests passed, zero skipped |
| Physical Apple TV | Owner-confirmed installation, pairing and basic playback on 0.3.0; exact model/tvOS and 0.4.0 UI still need device verification |
| Signing/archive/export/upload | Passed; dedicated identity |
| Apple processing | Complete |
| TestFlight build/group | 0.3.0 (1) Testing; one tester/one build |
| Requested invitation | jtillnes2@yahoo.com shown Invited |

Remaining physical-device checks: verify the updated image tiles and photo navigation, representative audio/aspect/seek, continuous transitions and return focus. A future reboot should also confirm the configured boot trigger in practice.
