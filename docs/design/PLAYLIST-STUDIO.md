# Playlist studio — design and verification

Implemented 2026-10-01 for mvideo 0.5.0. The desktop reference is [06-playlist-studio.png](06-playlist-studio.png), generated with the built-in Image Gen tool, then implemented as React controls and real server data. No screenshot is used as interactive UI.

## Generation brief

Create a polished desktop companion for mvideo, using its charcoal, warm-white and amber visual direction. Show a flat three-column workspace: a playlist sidebar, searchable/filterable music-video library, and an ordered Eurodance playlist. Include New playlist, three named starter mixes, search, field and decade selectors, pagination, Add, Rename, Delete, Save changes, a saved indicator, drag grips, numbered rows and up/down/remove buttons. Use restrained borders and natural 16:9 video imagery. Avoid decorative cards, promotional sections, gradients and dashboard metrics. The result should be a practical library editor with readable controls. Generated example tracks and images are illustrative; the running product must use the existing catalog.

The generated reference is 1536 × 1024. It was used directly as the visual reference; production thumbnails come from the user's library, not the generated artist likenesses.

## Browser verification

Used the Codex in-app browser through `cua_repl`, first against a separate local copy of the catalog, then against the deployed Windows HTTPS server. Verified pairing, creating a playlist, search, adding songs, duplicate prevention, rename, save, reload, drag reordering and persisted order. A disposable local playlist was removed after verification. Production starters were read and displayed without changing their curated order.

Desktop was checked at the reference's native 1536 × 1024 dimensions, mobile at 390 × 844, and the normal browser viewport after resetting the override. Screenshots were captured with the browser screenshot API. The reference, final desktop screenshot and mobile editor screenshot were opened with `view_image` in the same visual QA pass. Mobile document width equals viewport width; the library and editing controls remain reachable with no horizontal document overflow.

Evidence: [deployed desktop screenshot](playlist-studio-live.jpeg); additional local screenshots in ignored `output/playlist-mobile-library.jpeg` and `output/playlist-mobile-editor.jpeg`. Apple TV playlist overview/detail screenshots are in ignored `output/playlists-tvos/`.

## Fidelity ledger

| Comparison | Reference and rendered evidence | Resolution |
| --- | --- | --- |
| Layout and containers | Header, left playlist rail, central library, right ordered editor in both. Flat lists and fine separators, no added card grid. | Preserved. Sidebar is 230px instead of approximately 276px to leave more room for real titles. |
| Copy | mvideo, Playlist studio, Connected, Disconnect, Playlists, New playlist, Your library, filter labels, Rename, Delete, Save changes, saved status and drag instruction match. | Intentional additions: real counts, fuller descriptions, Added states, Reload saved playlist. Actual search/results and server playlist order replace four illustrative rows. No unrelated promotional copy. |
| Typography | Sans-serif hierarchy, bold artist/name, lighter title/year, compact status and toolbar text. | Explicit 14px controls/body rows, 25px workspace headings, 12–13px secondary text. Mobile wraps long names without clipping controls. |
| Palette and states | Near-black background, warm-white text, amber primary controls/selection and green saved/connected feedback. | Fixed the selected playlist's hover style so it retains amber. Disabled Save changes is intentionally muted while clean. No decorative gradient added. |
| Imagery | Natural 16:9 thumbnail cells in both library and ordered list. | Uses actual signed catalog thumbnails. Generated scenes and duration labels are intentionally omitted; the public catalog response does not expose durations. |
| Icons | Outline plus, search, check, grip, chevrons and remove X in the reference and implementation. | Lucide components preserve the visual style; native image dragging disabled so row grips and images do not compete. |
| Density and scrolling | The reference contains four illustrative rows; real playlists contain 24–42 songs. | Independent desktop list scrolling keeps filters and save controls available. Library pagination covers the full collection. |
| Responsive behavior | Reference is desktop-only. | On narrow screens, playlists form a horizontal strip and library/editor stack. Thumbnail/year columns collapse in the editor; Add and up/down buttons support touch and keyboard. |

Above-the-fold copy comparison passed with the intentional data/functional differences above. Functional QA found and fixed drag-enter/drop handling, and visual QA fixed the selected hover color. The implementation was faithfully verified against the reference with these documented adaptations; no material unexplained visual mismatches remain.
