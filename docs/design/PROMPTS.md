# Image-generation prompts

Date: 2026-10-01. Mode: built-in `image_gen.imagegen`; no CLI/API fallback. Opaque backgrounds. All initial requests were independent generations using the same written design system. Targeted edits used the corresponding generated image as the edit target.

These prompts are provenance for review concepts, not implementation specifications or claims about the actual media library.

## 01-home

````text
Use case: ui-mockup
Asset type: high fidelity Apple TV music video app interface concept, one complete full-screen landscape 16:9 screen, target 2560x1440.
Design system: app name "mvideo" in small elegant lowercase bold sans serif at upper left. Premium cinematic editorial music library for a personal collection of 15,000+ local music videos. Near-black charcoal background, warm off-white large clean sans-serif typography, subtle muted amber accent, natural photographic color, very gentle gradients from hero photography into charcoal. Beautiful balanced negative space. Extremely polished and plausible tvOS app, designed to read across a living room. Big remote-selectable targets, generous screen safe margins, only one currently focused interactive element with a bright ivory rounded border and slight elevation. Film stills in wide 16:9 cards, artist names and song names below cards. Persistent top navigation in a horizontal centered row reads "Home   Search   Artists   Years   Decades". Small app logo at left. All content within safe margins. No mouse cursor, no browser chrome, no device frame, no annotations, no tiny dense UI, no fake 4K labels, no music streaming subscription elements, no technical server/IP/file-format details. This is a static illustrative design mockup, not a working product. Exact requested UI copy legible and correctly spelled. Render only the app screen.
Screen: HOME. Top "Home" navigation subtly active. Expansive moody widescreen hero occupying top two thirds, evocative black-and-white and blue-toned portrait imagery of Norwegian synth-pop trio a-ha on the right, fading gently into dark negative space on the left.
Left hero content: small eyebrow "FROM YOUR COLLECTION", very large headline "Your own music television.", subtitle "15,000+ videos. Every era. All yours." Below, two large pill actions: focused ivory "Shuffle all" with shuffle icon, secondary dark glass "Browse artists".
Bottom third: section title "Tonight's rotation" and a single generous row of four full landscape video thumbnails with readable labels below. Cards: "a-ha" / "Take On Me · 1985" with pencil-sketch music-video imagery; "Tears for Fears" / "Everybody Wants to Rule the World · 1985" with sunny desert-road imagery; "Madonna" / "Like a Prayer · 1989" with warm theatrical performance imagery; "David Bowie" / "Let's Dance · 1983" with red-lit art-rock imagery. Editorial hero feels atmospheric without sacrificing readable controls. No additional rows needed.
````

## 02-search

````text
Use case: ui-mockup
Asset type: high fidelity Apple TV music video app interface concept, one complete full-screen landscape 16:9 screen, target 2560x1440.
Design system: app name "mvideo" in small elegant lowercase bold sans serif at upper left. Premium cinematic editorial music library for a personal collection of 15,000+ local music videos. Near-black charcoal background, warm off-white large clean sans-serif typography, subtle muted amber accent, natural photographic color, very gentle gradients from hero photography into charcoal. Beautiful balanced negative space. Extremely polished and plausible tvOS app, designed to read across a living room. Big remote-selectable targets, generous screen safe margins, only one currently focused interactive element with a bright ivory rounded border and slight elevation. Film stills in wide 16:9 cards, artist names and song names below cards. Persistent top navigation in a horizontal centered row reads "Home   Search   Artists   Years   Decades". Small app logo at left. All content within safe margins. No mouse cursor, no browser chrome, no device frame, no annotations, no tiny dense UI, no fake 4K labels, no music streaming subscription elements, no technical server/IP/file-format details. This is a static illustrative design mockup, not a working product. Exact requested UI copy legible and correctly spelled. Render only the app screen.
Screen: SEARCH. Top "Search" navigation subtly active. Large title "Find your next video". Under it a generous search field with magnifying glass, query "a-ha", and a microphone icon. Across under field large filter pills "All", "Artists", "Titles", "Years", with All selected in amber.
Layout: left third is an elegant TV remote on-screen keyboard, a compact alphabetical 6-column grid of large letter keys A-Z plus space, delete and clear. Focus ring on the letter A. A helper above says "Search artist, title or year". Right two thirds are results, without crowding the keyboard.
Results: heading "Artist", one large horizontal artist result featuring a circular black-and-white band portrait, name "a-ha" in large type, secondary "24 videos", and chevron.
Below: heading "Music videos" and two fully visible wide 16:9 thumbnail cards, side by side: "Take On Me" / "a-ha · 1985" with pencil-sketch imagery, "The Sun Always Shines on T.V." / "a-ha · 1985" with gothic stage imagery. A small amber text action "Shuffle results" with shuffle icon beside heading. Search must feel like a real remote-driven TV screen with outstanding large readable text, not a desktop web dashboard. No hero slogan here.
````

## 03-artist

````text
Use case: ui-mockup
Asset type: high fidelity Apple TV music video app interface concept, one complete full-screen landscape 16:9 screen, target 2560x1440.
Design system: app name "mvideo" in small elegant lowercase bold sans serif at upper left. Premium cinematic editorial music library for a personal collection of 15,000+ local music videos. Near-black charcoal background, warm off-white large clean sans-serif typography, subtle muted amber accent, natural photographic color, very gentle gradients from hero photography into charcoal. Beautiful balanced negative space. Extremely polished and plausible tvOS app, designed to read across a living room. Big remote-selectable targets, generous screen safe margins, only one currently focused interactive element with a bright ivory rounded border and slight elevation. Film stills in wide 16:9 cards, artist names and song names below cards. Persistent top navigation in a horizontal centered row reads "Home   Search   Artists   Years   Decades". Small app logo at left. All content within safe margins. No mouse cursor, no browser chrome, no device frame, no annotations, no tiny dense UI, no fake 4K labels, no music streaming subscription elements, no technical server/IP/file-format details. This is a static illustrative design mockup, not a working product. Exact requested UI copy legible and correctly spelled. Render only the app screen.
Screen: ARTIST DETAIL, a-ha. Top "Artists" navigation subtly active. Upper half is large atmospheric black-and-white band photography of a-ha on the right, fading to near-black on left. Left: small "ARTIST", massive "a-ha", subtitle "24 videos in your library". Short large readable biography copy on two lines: "Soaring melodies, cinematic sound." and "An unmistakable voice in synth-pop." This is illustrative editorial text. Under it three large pill buttons: focused ivory "Shuffle artist", dark glass "Play all", dark glass "Biography". Small secondary text "Biography · Last.fm" near this area, restrained.
Lower half: heading "Music videos" with small filter pills "All years", "1980s", "1990s" to right; then three generous landscape thumbnail cards: "Take On Me" / "1985" with pencil-sketch imagery, "The Sun Always Shines on T.V." / "1985" with gothic concert imagery, "Stay on These Roads" / "1988" with windswept coastline imagery. Along bottom just enough room for subtle section title "Artist photos" and the top edges of a photo strip suggesting vertical continuation. Balance biography, play actions, and the user's local videos. No album cover grid.
````

## 04-year

````text
Use case: ui-mockup
Asset type: high fidelity Apple TV music video app interface concept, one complete full-screen landscape 16:9 screen, target 2560x1440.
Design system: app name "mvideo" in small elegant lowercase bold sans serif at upper left. Premium cinematic editorial music library for a personal collection of 15,000+ local music videos. Near-black charcoal background, warm off-white large clean sans-serif typography, subtle muted amber accent, natural photographic color, very gentle gradients from hero photography into charcoal. Beautiful balanced negative space. Extremely polished and plausible tvOS app, designed to read across a living room. Big remote-selectable targets, generous screen safe margins, only one currently focused interactive element with a bright ivory rounded border and slight elevation. Film stills in wide 16:9 cards, artist names and song names below cards. Persistent top navigation in a horizontal centered row reads "Home   Search   Artists   Years   Decades". Small app logo at left. All content within safe margins. No mouse cursor, no browser chrome, no device frame, no annotations, no tiny dense UI, no fake 4K labels, no music streaming subscription elements, no technical server/IP/file-format details. This is a static illustrative design mockup, not a working product. Exact requested UI copy legible and correctly spelled. Render only the app screen.
Screen: YEAR DETAIL 1985. Top "Years" navigation subtly active. Upper half editorial composition: enormous "1985" in ivory left, eyebrow "THE YEAR IN MUSIC VIDEOS", subtitle "312 videos in your library". Huge ghosted outline numerals very subtly in backdrop plus atmospheric sepia and blue music-video photography on right, not busy collage.
Buttons below title: focused ivory "Shuffle 1985" and dark glass "Play all".
Below hero a large horizontal year rail "1982   1983   1984   1985   1986   1987   1988" with active 1985 highlighted amber. On same visual zone a subtle action "Explore the 1980s" with right chevron.
Lower half: heading "Music videos" and small sort pill "Artist A–Z". Three spacious landscape thumbnails: "a-ha" / "Take On Me", "Dire Straits" / "Money for Nothing", "Tears for Fears" / "Everybody Wants to Rule the World". Imagery respectively pencil animation, low-poly neon 1980s animation, open desert road. All videos are sample entries from this year, no global shuffle on this page. Strong hierarchy and room to breathe.
````

## 05-decade

````text
Use case: ui-mockup
Asset type: high fidelity Apple TV music video app interface concept, one complete full-screen landscape 16:9 screen, target 2560x1440.
Design system: app name "mvideo" in small elegant lowercase bold sans serif at upper left. Premium cinematic editorial music library for a personal collection of 15,000+ local music videos. Near-black charcoal background, warm off-white large clean sans-serif typography, subtle muted amber accent, natural photographic color, very gentle gradients from hero photography into charcoal. Beautiful balanced negative space. Extremely polished and plausible tvOS app, designed to read across a living room. Big remote-selectable targets, generous screen safe margins, only one currently focused interactive element with a bright ivory rounded border and slight elevation. Film stills in wide 16:9 cards, artist names and song names below cards. Persistent top navigation in a horizontal centered row reads "Home   Search   Artists   Years   Decades". Small app logo at left. All content within safe margins. No mouse cursor, no browser chrome, no device frame, no annotations, no tiny dense UI, no fake 4K labels, no music streaming subscription elements, no technical server/IP/file-format details. This is a static illustrative design mockup, not a working product. Exact requested UI copy legible and correctly spelled. Render only the app screen.
Screen: DECADE DETAIL 1980s. Top "Decades" navigation subtly active. Distinct from year screen: top left eyebrow "A DECADE OF MUSIC TELEVISION", huge headline "The 1980s", supporting "1980–1989 · 2,840 videos". Right half of upper hero is tasteful photomontage of era music imagery: monochrome pop portrait, analog synthesizer stage, pencil-sketch music-video frame, warm red performance lighting; all merged quietly into charcoal rather than separate busy cards.
Under headline: focused ivory button "Shuffle the 1980s", secondary glass button "Play all".
Middle zone: heading "Choose a year", ten compact but remote-friendly year tiles arranged in one spacious horizontal row. Exact chronological labels "1980", "1981", "1982", "1983", "1984", "1985", "1986", "1987", "1988", "1989". Each has muted photographic texture or solid charcoal, year in large ivory text; 1985 uses subtle amber fill as an emphasized discovery tile but no second focus outline.
Bottom zone heading "From your collection", three wide video thumbnails: "David Bowie" / "Let's Dance · 1983"; "a-ha" / "Take On Me · 1985"; "Madonna" / "Like a Prayer · 1989". Small unobtrusive previous/next decade actions "1970s" and "1990s" near the decade heading. Keep all elements comfortably visible and legible at television distance.
````

## Targeted refinements

### 02-search

````text
Use case: ui-mockup. Edit this Apple TV music video app search mockup. Preserve the entire layout, typography, images, colors, all text and controls unchanged. Make exactly one improvement: add a large remote-selectable dark rounded keyboard toggle button labelled "123" below the alphabet keyboard at the lower left, visually matching existing keys, to make searching numeric years possible. Keep the existing alphabet keyboard, Space, delete and Clear keys unchanged. No extra focus ring on the new key; retain focus on A. Preserve landscape 16:9 canvas and sharp high fidelity UI.
````

### 04-year

````text
Use case: ui-mockup. Edit this Apple TV music video app year page. Preserve all layout positions, images, text, video cards, typography, margins, palette, dimensions and 16:9 canvas. Make only these corrections: replace the triangular play icon inside the ivory "Shuffle 1985" button with a true two-crossed-arrows shuffle icon; keep the secondary Play all button play icon. Remove the background poster and its slogan from the top-right hero photograph, filling that small area with the existing atmospheric industrial landscape. Style both hero buttons with pill corners matching a premium tvOS interface. Change the top-navigation active Years item from its gray capsule to warm-white text with a small amber underline, without capsule, matching a thin underline active tab. Nothing else changes.
````

### 05-decade

````text
Use case: ui-mockup. Edit this Apple TV music video app decade mockup. Preserve the entire layout, all UI labels, all ten years 1980 through 1989, photography, card positions, typography, palette and 16:9 canvas. Remove only incidental decorative lettering from inside the hero photo collage: remove the hand-lettered phrases at top right and below the synthesizer performer, filling with surrounding photo texture. In the 1981 year tile remove the MTV logo and replace with atmospheric red stage lighting, keeping the white year 1981. In the 1989 year tile remove the background phrase but preserve the white foreground 1989. Make both hero buttons pill shaped, otherwise keep their size, placement and content. Do not remove any actual navigation, button labels, headings or song metadata. No other modifications.
````
