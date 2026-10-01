# mvideo

An Apple TV music video app concept for a personal video library hosted on a Windows PC.

**Status: visual exploration, awaiting approval.** This repository contains design mockups and notes only. There is no runnable Apple TV app or PC server yet.

## Intended experience

- Search a collection of 15,000+ videos by artist, song title, and year.
- Explore artist pages with biographies, photos, and videos available in the local library.
- Browse individual years and decades.
- Play individual videos or shuffle the whole library, an artist, a year, or a decade.

The source collection is at `L:\MusicVideos\`, with filenames generally following `Artist - Song (Year)`. Formats reported by the owner include MP4, AVI, MKV, MPG, VOB, WebM, and WMV. Format compatibility is a future engineering task and has not been tested.

## Visual concept

A cinematic charcoal interface, large photography, warm white type, amber navigation accents, and visible remote focus. The examples use 1980s music to show a coherent set of screens; the intended app covers every era present in the collection.

| Screen | Preview | Main behavior illustrated |
| --- | --- | --- |
| Home | [01-home.png](docs/design/01-home.png) | Library-wide shuffle and video discovery |
| Search | [02-search.png](docs/design/02-search.png) | Artist/title/year search, keyboard and results |
| Artist | [03-artist.png](docs/design/03-artist.png) | Biography, images, local videos and artist shuffle |
| Year | [04-year.png](docs/design/04-year.png) | Videos from 1985, adjacent years and year shuffle |
| Decade | [05-decade.png](docs/design/05-decade.png) | Ten years, decade navigation and decade shuffle |

See the [design review](docs/design/README.md) for all five images, intended interactions and the approval boundary. [Generation prompts](docs/design/PROMPTS.md) are retained for revisions.

The artwork, artist photos, biography copy, thumbnails, sample videos and per-page counts are illustrative AI-generated content. They were not retrieved from the media library, Last.fm, Wikipedia or fanart.tv. The mockups do not establish real playback, metadata or device compatibility.

## Planning after design approval

1. Confirm the visual direction and remote navigation behavior.
2. Inspect a read-only sample of the collection to establish filename parsing, video/audio formats, and thumbnail needs.
3. Design and verify a PC library/streaming service and the connection over the owner's Tailscale network.
4. Evaluate playback options for compatible and incompatible formats before committing to an implementation.
5. Define metadata matching, caching and attribution for Last.fm or Wikipedia biographies and fanart.tv artwork.
6. Move native Apple TV implementation to the Mac and validate on an actual Apple TV.

The local `.env` contains the owner's provider configuration (`LAST_FM`, `LAST_FM_SECRET`, `FANART_TV`) and is excluded from Git. No provider credentials were read or used for these mockups.
