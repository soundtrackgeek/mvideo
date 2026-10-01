# Filename repair audit — 2026-10-01

Inspected all **15,559** video filenames on the mounted Windows media share. The strict parser reported **114** incomplete/ambiguous names; additional whitespace and invisible-character checks, plus the owner's year decisions, produced **183 renames and one move aside**. Applying this exact plan to the audited inventory leaves **15,558** videos with no filename-parser warnings and no destination collisions. These are proposed changes; the Windows command with `-Apply` must run against the live catalog before they take effect.

## Complete year decision list

The owner supplied these decisions on 2026-10-01. No release years were guessed.

| Current filename | Decision |
| --- | --- |
| Farrenheit - Fool In Love.mp4 | 1987 |
| Matt Cox - Washed It All Away.mp4 | Unknown: move aside for now |
| Sugar Ray - Someday.mp4 | 1999 |
| ABC - Stranger Things (1997s).webm | 1997 |
| Lethal - Immune (199!).mp4 | 1990 |
| Unearth - Black Hearts Now Reign (20049.mp4 | 2004 |
| Miss Kittin & The Hacker (1982).mpg | Title 1982, year 1998 |

Other existing clear years are preserved, including when repairing extra/missing parentheses or removing technical suffixes. Upload dates and filesystem timestamps are not used as release years. This is a filename-format audit; it does not independently verify the musical identity or historical year of every already well-formed name.

## Apply the reviewed names

From the updated checkout on Windows, stop the loudness scan with Ctrl+C and close active mvideo playback/playlist editing. Preview, then apply:

```powershell
git pull --ff-only
.\scripts\windows-fix-filenames.ps1
.\scripts\windows-fix-filenames.ps1 -Apply
```

The preview lists exact actions, conflicts, names not found in the catalog, already completed actions and any other catalog filenames with parser warnings. For the audited library, expect **184 ready actions** before the first run. `-Library`, `-State` and `-PythonPath` select the installation as in the loudness launcher; by default the launcher reuses the installed service configuration and Python. `-Plan path.json` can select another explicit reviewed plan. The portable CLI is `mvideo fix-filenames` and `mvideo fix-filenames --apply`.

The command backs up SQLite, locks out concurrent library/loudness scans, renames only the listed paths, and migrates playlist entries, metadata overrides and loudness measurements to the filename-derived IDs. Playlist order is preserved and playlist versions advance so stale browser drafts cannot overwrite updated references. It does not decode, re-encode or overwrite source media. Existing thumbnails/conversions may be regenerated under the new IDs. Refresh/reopen the Apple TV library after completion; restart loudness analysis to continue using its saved measurements. No service deployment or Apple TV update is needed.

Matt Cox's file moves to the sibling folder **`L:\MusicVideos - Needs Review`** for the current `L:\MusicVideos` library, retaining its original filename. For another library folder the destination is its name plus ` - Needs Review`, next to that folder on the same volume. The catalog marks the video unavailable and keeps its playlist references, overrides and measurements. To restore it later, move it back under its original name and scan; then supply its confirmed year through a new reviewed repair. The command never moves it to the recycle bin or deletes its content.

If interrupted, rerun `-Apply`: a committed per-file journal recovers a move interrupted before the catalog update. An automatic scan's matching, unreferenced destination row can be reconciled on resume. If that row has since acquired playlist references, overrides or measurements, recovery stops for manual reconciliation instead of merging user data. Changed sources or conflicting destinations also stop the operation. Keep the reported SQLite backup and `filename_renames` journal; the backup alone does not undo filesystem moves. Do not manually rename listed files before applying the plan: that bypasses catalog migration.

The two Thunder “Dirty Love” files are both kept. The additional file becomes `Thunder - Dirty Love (Additional Copy) (1990).mp4`; this label distinguishes files without claiming a different musical mix.

## Identification evidence

- `Alagados- De Frente Pro Crime`: embedded media tags identify the title and ParalamasVEVO source; [original video](https://www.youtube.com/watch?v=o7N76QdXc6E). A plus sign separates the medley titles because a slash is invalid in Windows filenames.
- [Army Of Lovers — Israelism](https://www.youtube.com/watch?v=2ZM6gVXXNCI) and [My Army Of Lovers](https://www.youtube.com/watch?v=P8MQ8tJhxU8) resolve the two artist-free titles.
- [Donald Fagen — Snowbound](https://www.imdb.com/title/tt6692790/fullcredits/) distinguishes the artist from director Michel Gondry.
- [Lodger personnel/discography](https://umdmusic.com/default.asp?Lang=English&Umd=L34342&View=I) identifies Pearl Lowe as a band member, not part of the song title.
- [Fluffy — Black Eye](https://www.imdb.com/title/tt6829080/) confirms the title without the upload suffix “Best”.
- [Quicksilver soundtrack](https://www.imdb.com/title/tt0091814/soundtrack/) confirms “One Summer Day/Dueling Bikes”; parentheses retain the second title in a Windows-safe filename.
- [Miss Kittin & The Hacker — 1982](https://www.allmusic.com/artist/miss-kittin-the-hacker-mn0000497434) identifies the numeric song title. The owner supplied the year 1998.

- [Drugstore — El President](https://music.apple.com/gb/song/1652981936) corrects the swapped artist and song.
- [Gabrielle — Every Step](https://www.youtube.com/watch?v=d9U36_BvsQc) confirms the title without the stray diaeresis; the existing filename year is retained.
- [Elton John & Millie Jackson — Act Of War](https://www.officialcharts.com/songs/elton-john-and-millie-jackson-act-of-war/) confirms the title without a duplicated year.

## Reviewed rename list

| Current filename | Proposed filename |
| --- | --- |
| 5th Ward Boyz  One Night Stand (1995).mp4 | 5th Ward Boyz - One Night Stand (1995).mp4 |
| Aaliyah -  Try Again (2000).mp4 | Aaliyah - Try Again (2000).mp4 |
| ABBA - Does Your Mother Know  (1979).mpg | ABBA - Does Your Mother Know (1979).mpg |
| ABC - Stranger Things (1997s).webm | ABC - Stranger Things (1997).webm |
| Alagados- De Frente Pro Crime (1986).mp4 | Os Paralamas Do Sucesso - Alagados + De Frente Pro Crime (1986).mp4 |
| Alex Call _Just Another Saturday Night (1983).mp4 | Alex Call - Just Another Saturday Night (1983).mp4 |
| Amy Grant  The Things We Do For Love (1996).mp4 | Amy Grant - The Things We Do For Love (1996).mp4 |
| B. A.  Robertson - Kool In the Kaftan (1980).mp4 | B. A. Robertson - Kool In the Kaftan (1980).mp4 |
| Barnes & Barnes – Fish Heads (1980) [HQ] (1080p_30fps_H264-128kbit_AAC).mp4 | Barnes & Barnes - Fish Heads (1980).mp4 |
| Barnes & Barnes_ Love Tap (1981).mp4 | Barnes & Barnes - Love Tap (1981).mp4 |
| Berlin ‎- Sex (1984).mp4 | Berlin - Sex (1984).mp4 |
| Billy Joel - Say Goodbye To Hollywood (1981)).mp4 | Billy Joel - Say Goodbye To Hollywood (1981).mp4 |
| Bomb The Bass - The Air You Breathe (1991.mp4 | Bomb The Bass - The Air You Breathe (1991).mp4 |
| Boy George ‎feat. Hi-Gate - High Fashion (2003).mp4 | Boy George feat. Hi-Gate - High Fashion (2003).mp4 |
| Boyz II Men - Thank You(1995).mp4 | Boyz II Men - Thank You (1995).mp4 |
| Brothers Like Outlaw - Good Vibrations (1992) .webm | Brothers Like Outlaw - Good Vibrations (1992).webm |
| BUSH - Warm Machine  (2000).mp4 | BUSH - Warm Machine (2000).mp4 |
| Busta Rhymes ‎- Turn It Up (1998).mp4 | Busta Rhymes - Turn It Up (1998).mp4 |
| Busta Rhymes ‎- Woo-Hah!! Got You All In Check (1996).mp4 | Busta Rhymes - Woo-Hah!! Got You All In Check (1996).mp4 |
| C-Block   So Strung Out (The Distance & Riddick Edit) (1996).mp4 | C-Block - So Strung Out (The Distance & Riddick Edit) (1996).mp4 |
| C-BLOCK   The Future Is So Bright (2000).mp4 | C-BLOCK - The Future Is So Bright (2000).mp4 |
| Cheech & Chong  - I'm Not Home Right Now (1985).mp4 | Cheech & Chong - I'm Not Home Right Now (1985).mp4 |
| Dave Hollister -  One Woman Man (2000).mp4 | Dave Hollister - One Woman Man (2000).mp4 |
| David Bowie  When The Wind Blows (1986).mp4 | David Bowie - When The Wind Blows (1986).mp4 |
| David Hasselhoff  - Is Everybody Happy (1989).mp4 | David Hasselhoff - Is Everybody Happy (1989).mp4 |
| David Hasselhoff  - Je T´Aime Means I Love You (1989).mp4 | David Hasselhoff - Je T´Aime Means I Love You (1989).mp4 |
| Deacon Blue - Hang Your Head (1993) .mp4 | Deacon Blue - Hang Your Head (1993).mp4 |
| Deja Gruv feat  Rakim -  You're Not Around (1996).mp4 | Deja Gruv feat Rakim - You're Not Around (1996).mp4 |
| Diana Ross - Upside Down (1980)).mp4 | Diana Ross - Upside Down (1980).mp4 |
| DJ Spooky Peace In Zaire (1999).mp4 | DJ Spooky - Peace In Zaire (1999).mp4 |
| Dj Taylor & Flow Gott tanzte (1999).mp4 | Dj Taylor & Flow - Gott tanzte (1999).mp4 |
| DMX, Method Man, Nas & Ja Rule ‎- The Grand Finale (1998).mp4 | DMX, Method Man, Nas & Ja Rule - The Grand Finale (1998).mp4 |
| Donna Summer ‎- On The Radio (1979).webm | Donna Summer - On The Radio (1979).webm |
| Down Low  I Wonder Why 1999  Youtube (1999).mp4 | Down Low - I Wonder Why (1999).mp4 |
| Dr  Hook - Sexy Eyes (1980).mp4 | Dr Hook - Sexy Eyes (1980).mp4 |
| Dr. Bombay- S.O.S (1998).mp4 | Dr. Bombay - S.O.S (1998).mp4 |
| El President - Drugstore(1998).mp4 | Drugstore - El President (1998).mp4 |
| Elton John & Millie Jackson - Act of war  1985 (1985).mp4 | Elton John & Millie Jackson - Act Of War (1985).mp4 |
| Erasure – Voulez Vous (1992).mp4 | Erasure - Voulez Vous (1992).mp4 |
| EURYTHMICS  - Never Gonna Cry Again  (1981).mp4 | EURYTHMICS - Never Gonna Cry Again (1981).mp4 |
| Eurythmics - There Must Be An Angel (Playing With My Heart)(1985).mp4 | Eurythmics - There Must Be An Angel (Playing With My Heart) (1985).mp4 |
| Faith Hill  I Can't Do That Anymore (1996).mp4 | Faith Hill - I Can't Do That Anymore (1996).mp4 |
| Falco - Junge Römer - HQ 720p (1984).mp4 | Falco - Junge Römer (1984).mp4 |
| Farrenheit - Fool In Love.mp4 | Farrenheit - Fool In Love (1987).mp4 |
| Feeder - Crash - Official Video (1997).mp4 | Feeder - Crash (1997).mp4 |
| Feeder - Stereo World - Official Video (1996).mp4 | Feeder - Stereo World (1996).mp4 |
| Feeder - Tangerine - Official Video (1997).mp4 | Feeder - Tangerine (1997).mp4 |
| FENIX TX -All My Fault HD720 (1997).mp4 | FENIX TX - All My Fault (1997).mp4 |
| Flipmode Squad ‎- Everybody On The Line Outside (1998).mp4 | Flipmode Squad - Everybody On The Line Outside (1998).mp4 |
| Flipmode Squad ‎– Cha Cha Cha (1998).mp4 | Flipmode Squad - Cha Cha Cha (1998).mp4 |
| Fluffy Black Eye Best (1997).mp4 | Fluffy - Black Eye (1997).mp4 |
| Frank Sinatra & Bono ‎– I've Got You Under My Skin (1993).mp4 | Frank Sinatra & Bono - I've Got You Under My Skin (1993).mp4 |
| Full Force   Kiss Those Lips (1989).webm | Full Force - Kiss Those Lips (1989).webm |
| Gabrielle - Every Step¨(2018).mp4 | Gabrielle - Every Step (2018).mp4 |
| Geggy Tah – Whoever You Are (1996).mp4 | Geggy Tah - Whoever You Are (1996).mp4 |
| George Benson - Turn Your Love Around  (1981).mp4 | George Benson - Turn Your Love Around (1981).mp4 |
| Gerry Rafferty - Baker Street (1978 ).mpg | Gerry Rafferty - Baker Street (1978).mpg |
| Gowan ~ Strange Animal (1985).mp4 | Gowan - Strange Animal (1985).mp4 |
| Grace Jones - I've Seen That Face Before (1981)).mp4 | Grace Jones - I've Seen That Face Before (1981).mp4 |
| Grandmaster Melle Mel ‎- White Lines (1983).mp4 | Grandmaster Melle Mel - White Lines (1983).mp4 |
| Gregory Abbott - I Got The Feeling(1987).mp4 | Gregory Abbott - I Got The Feeling (1987).mp4 |
| Harry Connick Jr. The Bare Necessities (1991).mp4 | Harry Connick Jr. - The Bare Necessities (1991).mp4 |
| Haysi Fantayzee · Sister Friction (1983).mp4 | Haysi Fantayzee - Sister Friction (1983).mp4 |
| Helen Terry & Ray Parker Jr. ~ One Summer Day_Dueling Bikes (1986).mp4 | Helen Terry & Ray Parker Jr. - One Summer Day (Dueling Bikes) (1986).mp4 |
| Helium - Pat's Trick (1995) .mp4 | Helium - Pat's Trick (1995).mp4 |
| Icehouse  - No Promises (US Club Mix) (1986).mp4 | Icehouse - No Promises (US Club Mix) (1986).mp4 |
| Inner City ‎- Do You Love What You Feel (1989).mp4 | Inner City - Do You Love What You Feel (1989).mp4 |
| Israelism (1993).mpg | Army Of Lovers - Israelism (1993).mpg |
| Jaw -  Alec is Amused (2000).mp4 | Jaw - Alec is Amused (2000).mp4 |
| Jeanette  - Go Back (2000).mp4 | Jeanette - Go Back (2000).mp4 |
| Jeff Beck - Ambitious(1985).mp4 | Jeff Beck - Ambitious (1985).mp4 |
| JellyBean ‎- Who Found Who (1987).webm | JellyBean - Who Found Who (1987).webm |
| John Lennon Imagine (1971).mp4 | John Lennon - Imagine (1971).mp4 |
| John Mellencamp  ft. Me'Shell Ndegeocello - Wild Night (1994).mp4 | John Mellencamp ft. Me'Shell Ndegeocello - Wild Night (1994).mp4 |
| Johnny Right -  I Wanna Be With You Tonight (1997).mp4 | Johnny Right - I Wanna Be With You Tonight (1997).mp4 |
| Journey - Don't Stop Believin (1981)'.mp4 | Journey - Don't Stop Believin' (1981).mp4 |
| Juliet Roberts I Want You (1994).mp4 | Juliet Roberts - I Want You (1994).mp4 |
| Kane Gang - Respect Yourself  (1984).mp4 | Kane Gang - Respect Yourself (1984).mp4 |
| Kate Bush - Army Dreamers (1980)).mp4 | Kate Bush - Army Dreamers (1980).mp4 |
| Keith Sweat ft Traci Hale  Just a Touch (1996).mp4 | Keith Sweat ft Traci Hale - Just a Touch (1996).mp4 |
| Kenny Rogers &  Dolly Parton -  Islands In The Stream (1983).mp4 | Kenny Rogers & Dolly Parton - Islands In The Stream (1983).mp4 |
| Kid Rock - Only God Knows Why (1998)).mp4 | Kid Rock - Only God Knows Why (1998).mp4 |
| Killswitch Engage - A Bid Farewell I(2004).mp4 | Killswitch Engage - A Bid Farewell I (2004).mp4 |
| Kings of Swing- You Know I Love Ya baby (1994).mp4 | Kings of Swing - You Know I Love Ya baby (1994).mp4 |
| Krayzie Bone- Thug Mentality (1999).mp4 | Krayzie Bone - Thug Mentality (1999).mp4 |
| Kreator -  Betrayer (1989).mp4 | Kreator - Betrayer (1989).mp4 |
| L7 - Stuck Here Again(1994).mp4 | L7 - Stuck Here Again (1994).mp4 |
| Laurent Voulzy-Paradoxal systeme (1992).mp4 | Laurent Voulzy - Paradoxal systeme (1992).mp4 |
| Lethal - Immune (199!).mp4 | Lethal - Immune (1990).mp4 |
| Limp Bizkit Take a look around (2000).mp4 | Limp Bizkit - Take a look around (2000).mp4 |
| Linga Nāc Dejot - Let's Dance(1988).mp4 | Linga Nāc Dejot - Let's Dance (1988).mp4 |
| Lionel Richie - Truly (1982)).mp4 | Lionel Richie - Truly (1982).mp4 |
| Lodger - Small Change - Pearl Lowe (1998).mp4 | Lodger - Small Change (1998).mp4 |
| Mack 10 -Only In California (1997).mp4 | Mack 10 - Only In California (1997).mp4 |
| Madonna - Don't Tell Me (2000) [HD] (2000).mp4 | Madonna - Don't Tell Me (2000).mp4 |
| Magazine 60 -  Rendez Vous Sur La Costa Del Sol (1985).webm | Magazine 60 - Rendez Vous Sur La Costa Del Sol (1985).webm |
| Malice Mizer- Le Ciel (1998).mp4 | Malice Mizer - Le Ciel (1998).mp4 |
| MARILYN · Calling Your Name (1983).mp4 | MARILYN - Calling Your Name (1983).mp4 |
| Mc Breed- Late Night Creep (1994).mp4 | Mc Breed - Late Night Creep (1994).mp4 |
| Meat Loaf - I'd Do Anything For Love  (But I Won't Do That) (1993).mp4 | Meat Loaf - I'd Do Anything For Love (But I Won't Do That) (1993).mp4 |
| Melissa Manchester – Thief Of Hearts (1984).webm | Melissa Manchester - Thief Of Hearts (1984).webm |
| Michael Bolton - (Sittin' On) The Dock Of The Bay(1988).mp4 | Michael Bolton - (Sittin' On) The Dock Of The Bay (1988).mp4 |
| Michel Gondry - Snowbound - Donald Fagen (1993).mp4 | Donald Fagen - Snowbound (1993).mp4 |
| MIKE & THE MECHANICS - Revolution  (1989).mp4 | MIKE & THE MECHANICS - Revolution (1989).mp4 |
| Miki Howard- Love Under New Management (1989).mp4 | Miki Howard - Love Under New Management (1989).mp4 |
| Miko Mission -Two For Love (1985).mp4 | Miko Mission - Two For Love (1985).mp4 |
| Mint Condition - So Fine(1993) (1993).mp4 | Mint Condition - So Fine (1993).mp4 |
| Miss Kittin & The Hacker (1982).mpg | Miss Kittin & The Hacker - 1982 (1998).mpg |
| Modern Rocketry - Homosexuality(1985).mp4 | Modern Rocketry - Homosexuality (1985).mp4 |
| Mondo Rock - Summer Of `81  (1981).mp4 | Mondo Rock - Summer Of `81 (1981).mp4 |
| Motörhead – Ace Of Spades (1980).mp4 | Motörhead - Ace Of Spades (1980).mp4 |
| Mozart - Symphony No  25 (1985).mp4 | Mozart - Symphony No 25 (1985).mp4 |
| My Army Of Lovers (1990).mpg | Army Of Lovers - My Army Of Lovers (1990).mpg |
| New Edition ft  Missy - You Don't Have To Worry (Remix) (1996).mp4 | New Edition ft Missy - You Don't Have To Worry (Remix) (1996).mp4 |
| Niagara -  Soleil D'hiver (1988).webm | Niagara - Soleil D'hiver (1988).webm |
| Nina Hagen - Smack Jack  (1982).mp4 | Nina Hagen - Smack Jack (1982).mp4 |
| NSYNC -Together Again (1997).mp4 | NSYNC - Together Again (1997).mp4 |
| Orbital – The Box (1996).mp4 | Orbital - The Box (1996).mp4 |
| Pat & Mick ‎– Shake Your Groove Thing (Extended Techno Mix) (1992).mp4 | Pat & Mick - Shake Your Groove Thing (Extended Techno Mix) (1992).mp4 |
| Paul Collins Beat  - Always Got You On My Mind (1983).mp4 | Paul Collins Beat - Always Got You On My Mind (1983).mp4 |
| Paul Young - L-O-V-E (Love) (2016.mp4 | Paul Young - L-O-V-E (Love) (2016).mp4 |
| Peaches -  Fuck the Pain Away (2000).mp4 | Peaches - Fuck the Pain Away (2000).mp4 |
| Peter Wolf  - Lights Out (1984).mp4 | Peter Wolf - Lights Out (1984).mp4 |
| Pink Floyd - Green Is The Colour 1969).mp4 | Pink Floyd - Green Is The Colour (1969).mp4 |
| Playahitty 1-2-3! (Train With Me) (1995).mp4 | Playahitty - 1-2-3! (Train With Me) (1995).mp4 |
| Poison - (Flesh & Blood) Sacrifice(1991).mp4 | Poison - (Flesh & Blood) Sacrifice (1991).mp4 |
| Prairie Oyster Will I Do (1992).mp4 | Prairie Oyster - Will I Do (1992).mp4 |
| Praying Mantis - This Time Gir (1991)l.mp4 | Praying Mantis - This Time Girl (1991).mp4 |
| Quad City DJ’s – C’mon N’ Ride It (1996).mp4 | Quad City DJ’s - C’mon N’ Ride It (1996).mp4 |
| Queen – Bohemian Rhapsody (1975).mp4 | Queen - Bohemian Rhapsody (1975).mp4 |
| R. Kelly  Sex Me (1993).webm | R. Kelly - Sex Me (1993).webm |
| Real McCoy - Automatic Lover (Call For Love) (1994)).mp4 | Real McCoy - Automatic Lover (Call For Love) (1994).mp4 |
| Righeira - Vamos A La Playa (1983) .webm | Righeira - Vamos A La Playa (1983).webm |
| Rob 'N' Raz & DLC ‎– Big City Life (1993).mp4 | Rob 'N' Raz & DLC - Big City Life (1993).mp4 |
| Rozalla - Everybody's Free (To Feel Good) (UK Version) (1991)].mp4 | Rozalla - Everybody's Free (To Feel Good) (UK Version) (1991).mp4 |
| Shade Sheist feat. Nate Dogg &  Kurupt - Where I Wanna Be (2000).mp4 | Shade Sheist feat. Nate Dogg & Kurupt - Where I Wanna Be (2000).mp4 |
| Sheena Easton - 9 to 5 (Morning Train) (1980)).mp4 | Sheena Easton - 9 to 5 (Morning Train) (1980).mp4 |
| Sheena Easton_ Take My Time (1981).mp4 | Sheena Easton - Take My Time (1981).mp4 |
| Smoothe Da Hustler   Hustler's Theme (1996).mp4 | Smoothe Da Hustler - Hustler's Theme (1996).mp4 |
| Soft Cell - Tainted Love (1991 Version)(1991).mp4 | Soft Cell - Tainted Love (1991 Version) (1991).mp4 |
| Soul Asylum - P-9‌ (1988).mp4 | Soul Asylum - P-9 (1988).mp4 |
| SoulDecision  - Faded (2000).mp4 | SoulDecision - Faded (2000).mp4 |
| Stone Temple Pilots -  No Way Out (2000).mp4 | Stone Temple Pilots - No Way Out (2000).mp4 |
| Stray Cats- I Won't Stand In Your Way (1983).mp4 | Stray Cats - I Won't Stand In Your Way (1983).mp4 |
| SubSonica & BluVertigo- Disco Labirinto (1999).mp4 | SubSonica & BluVertigo - Disco Labirinto (1999).mp4 |
| Sugar Ray - Someday.mp4 | Sugar Ray - Someday (1999).mp4 |
| Supertramp - You Win, I Lose  (1997).mp4 | Supertramp - You Win, I Lose (1997).mp4 |
| Tha Truth! Feat. Keith Murray - Makin' Moves(1997).mp4 | Tha Truth! Feat. Keith Murray - Makin' Moves (1997).mp4 |
| The Adventures - Drowning In the Sea of Love  (1988).mp4 | The Adventures - Drowning In the Sea of Love (1988).mp4 |
| The Art of Noise feat. Mahlathini And The Mahotella Queens ‎– Yebo! (1989).mp4 | The Art of Noise feat. Mahlathini And The Mahotella Queens - Yebo! (1989).mp4 |
| The Art Of Noise – Instruments Of Darkness (All Of Us Are One People) (The Prodigy Mix) (1991).mp4 | The Art Of Noise - Instruments Of Darkness (All Of Us Are One People) (The Prodigy Mix) (1991).mp4 |
| The Bluetones- Bluetonic (1995).mp4 | The Bluetones - Bluetonic (1995).mp4 |
| The Bluetones- Marblehead Johnson (1996).mp4 | The Bluetones - Marblehead Johnson (1996).mp4 |
| The Escape Club -  I'll Be There (1991).mp4 | The Escape Club - I'll Be There (1991).mp4 |
| The Human League -Tell Me When (1994).mp4 | The Human League - Tell Me When (1994).mp4 |
| The Kelly Family – Jingle Bells (1981).mp4 | The Kelly Family - Jingle Bells (1981).mp4 |
| The Kinks - State Of Confusion - 1983 (1983).mp4 | The Kinks - State Of Confusion (1983).mp4 |
| The Pharcyde - Otha Fish - 1993 (1993).mp4 | The Pharcyde - Otha Fish (1993).mp4 |
| The Reynolds Girls - I'd Rather Jack (1988)).mp4 | The Reynolds Girls - I'd Rather Jack (1988).mp4 |
| The S.O.S. Band - The Finest (1986)).mp4 | The S.O.S. Band - The Finest (1986).mp4 |
| The Twins - Not The Loving Kind  (1983).mp4 | The Twins - Not The Loving Kind (1983).mp4 |
| The Underdog Project - Summer Jam (DJ F.R.A.N.K.'s Summermix Short)(2000).mp4 | The Underdog Project - Summer Jam (DJ F.R.A.N.K.'s Summermix Short) (2000).mp4 |
| Thunder  River Of Pain (1995).mp4 | Thunder - River Of Pain (1995).mp4 |
| Thunder – Dirty Love (1990).mp4 | Thunder - Dirty Love (Additional Copy) (1990).mp4 |
| Tina Turner I Don't Wanna Fight (1993).mp4 | Tina Turner - I Don't Wanna Fight (1993).mp4 |
| Tom Jones feat. Mousse T  - Sexbomb (2000).mp4 | Tom Jones feat. Mousse T - Sexbomb (2000).mp4 |
| Toni Braxton - Another Sad Love Song  (Remix) (1993).mp4 | Toni Braxton - Another Sad Love Song (Remix) (1993).mp4 |
| Toto Coelo - Dracula's Tango (Sucker For Your Love)  (1982).mp4 | Toto Coelo - Dracula's Tango (Sucker For Your Love) (1982).mp4 |
| Unearth - Black Hearts Now Reign (20049.mp4 | Unearth - Black Hearts Now Reign (2004).mp4 |
| Urge Overkill - Ticket To L.A. ‌(1991).mp4 | Urge Overkill - Ticket To L.A. (1991).mp4 |
| UTE LEMPER ~ The Case Continues (2000).mp4 | UTE LEMPER - The Case Continues (2000).mp4 |
| Valerie Dore Get Closer (1984).mp4 | Valerie Dore - Get Closer (1984).mp4 |
| Van Halen - Right Now (1991.mp4 | Van Halen - Right Now (1991).mp4 |
| Vanessa Williams  - Darlin' I (1989).mp4 | Vanessa Williams - Darlin' I (1989).mp4 |
| wang chung fire in the twilight (1985).mp4 | Wang Chung - Fire in the Twilight (1985).mp4 |
| Ward Brothers - Cross That Bridge (Kitchen Sink Mix)(1986).mp4 | Ward Brothers - Cross That Bridge (Kitchen Sink Mix) (1986).mp4 |
| Warrior Fighting for the Earth -- MCA Records (1985).mp4 | Warrior - Fighting for the Earth (1985).mp4 |
| Was (Not Was) -  Papa Was A Rolling Stone (1990).webm | Was (Not Was) - Papa Was A Rolling Stone (1990).webm |
| Was (Not Was) - Spy In The House Of Love(1987).mp4 | Was (Not Was) - Spy In The House Of Love (1987).mp4 |
| Waveform 7 ft. Daddy D - Southside  (1997).mp4 | Waveform 7 ft. Daddy D - Southside (1997).mp4 |
| Womack & Womack - Celebrate The World (1988).mp4.mp4 | Womack & Womack - Celebrate The World (1988).mp4 |
| Young MC -That's The Way Love Goes (1991).mp4 | Young MC - That's The Way Love Goes (1991).mp4 |
| Zhané - Request Line(1997).mp4 | Zhané - Request Line (1997).mp4 |
