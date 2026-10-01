"""Match library artists using recording credits, never search rank alone."""
import re
import unicodedata
import uuid


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value).casefold() if c.isalnum())


def phrase(value):
    return '"' + re.sub(r'([\\"])', r'\\\1', value) + '"'


def match_artist(name, titles, request):
    # A distinctive song offers more evidence than a name-only result. Try at
    # most three library songs; reject conflicting credits and truncated results.
    matches, evidence = set(), []
    for title in titles[:3]:
        result = request('https://musicbrainz.org/ws/2/recording/', {
            'query': f'artist:{phrase(name)} AND recording:{phrase(title)}',
            'fmt': 'json', 'limit': 100,
        })
        if result.get('count', 0) > 100:
            continue
        song_matches = set()
        for recording in result.get('recordings', []):
            if normalized(recording.get('title', '')) != normalized(title):
                continue
            credits = recording.get('artist-credit', [])
            # Do not turn a collaboration into the identity of one participant.
            if len(credits) != 1:
                continue
            credit = credits[0]
            artist = credit.get('artist', {})
            names = [credit.get('name', ''), artist.get('name', '')]
            names += [alias.get('name', '') for alias in artist.get('aliases', [])]
            if normalized(name) not in {normalized(n) for n in names}:
                continue
            try:
                song_matches.add(str(uuid.UUID(artist.get('id', ''))))
            except (ValueError, AttributeError):
                continue
        matches.update(song_matches)
        if song_matches:
            evidence.append(title)
        if len(matches) > 1:
            return None, []
        # Two independent song credits are sufficient; one-song libraries can
        # still resolve from an unambiguous exact artist + recording credit.
        if len(evidence) >= 2:
            break
    return (next(iter(matches)), evidence) if len(matches) == 1 else (None, [])
