import json
import threading
import time

import httpx
import pytest

from mvideo.artist_match import match_artist, phrase
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.metadata import Metadata

MBID = 'b9a06530-1241-4162-836f-7b8e79deaa58'
OTHER = '7364dea6-ca9a-48e3-be01-b44ad0d19897'


def recording(title='These Are Days', mbid=MBID, name='10,000 Maniacs'):
    return {'title': title, 'artist-credit': [{'name': name, 'artist': {'id': mbid, 'name': name}}]}


@pytest.mark.parametrize('records,count,expected', [
    ([recording()], 1, MBID),
    ([recording(), recording(mbid=OTHER)], 2, None),
    ([recording(title='Different song')], 1, None),
    ([recording(name='Different artist')], 1, None),
    ([recording(mbid='not-a-uuid')], 1, None),
    ([recording()], 101, None),
    ([recording() | {'artist-credit': recording()['artist-credit'] * 2}], 1, None),
])
def test_recording_match_requires_unambiguous_song_credit(records, count, expected):
    result, _ = match_artist('10,000 Maniacs', ['These Are Days'], lambda *a: {'recordings': records, 'count': count})
    assert result == expected


def test_aliases_punctuation_conflicting_tracks_and_query_escaping():
    item = recording(name='Ten Thousand Maniacs')
    item['artist-credit'][0]['artist']['aliases'] = [{'name': '10.000 Maniacs'}]
    assert match_artist('10,000 Maniacs', ['These Are Days'], lambda *a: {'recordings': [item], 'count': 1})[0] == MBID
    responses = iter([{'recordings': [recording(title='First')], 'count': 1},
                      {'recordings': [recording(title='Second', mbid=OTHER)], 'count': 1}])
    assert match_artist('10,000 Maniacs', ['First', 'Second'], lambda *a: next(responses))[0] is None
    assert phrase('A "B" \\ C') == '"A \\"B\\" \\\\ C"'


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    monkeypatch.setenv('FANART_TV', 'test-only')
    monkeypatch.setenv('LAST_FM', 'test-only')
    settings = Settings(tmp_path/'media', tmp_path/'state'); settings.prepare()
    db = Database(settings.state/'library.sqlite3')
    with db.connect() as c:
        c.execute('''INSERT INTO videos(id,path,size,mtime,artist,title,year,raw_name,warnings)
            VALUES('one','one.mp4',1,1,'10,000 Maniacs','These Are Days',1992,'one','[]')''')
    value = Metadata(db, settings)
    yield value
    value.close()


def providers(url, params):
    if 'musicbrainz.org' in url:
        return {'recordings': [recording()], 'count': 1}
    if 'audioscrobbler' in url:
        return {'artist': {'name': '10,000 Maniacs', 'mbid': MBID, 'url': 'https://www.last.fm/music/10,000+Maniacs',
                           'bio': {'summary': 'An American alternative rock band with many releases in the library.'}}}
    assert url.endswith(MBID)
    return {'artistbackground': [{'url': 'http://assets.fanart.tv/artist.jpg'}]}


def test_automatic_artwork_replaces_old_negative_cache_and_is_shared(metadata):
    with metadata.db.connect() as c:
        c.execute('INSERT INTO metadata VALUES(?,?,?)', ('10,000 Maniacs', json.dumps({
            'state': 'needs_identity', 'images': [], 'biography': None}), int(time.time()) + 86400))
    calls = []
    metadata.request = lambda *a: (calls.append(a[0]), providers(*a))[1]
    data = metadata.artist('10,000 Maniacs')
    assert data['images'] == ['https://assets.fanart.tv/artist.jpg']
    assert data['identity_source'] == 'musicbrainz_recording'
    assert data['matched_tracks'] == ['These Are Days']
    assert data['mbid'] == MBID
    assert metadata.cached_artwork(['10,000 Maniacs']) == {'10,000 maniacs'}
    assert metadata.featured()['artist'] == '10,000 Maniacs'
    assert metadata.lookup('10,000 MANIACS')['pending'] is False
    assert len(calls) == 3
    with metadata.db.connect() as c:
        assert c.execute('SELECT count(*) FROM identities').fetchone()[0] == 0


def test_manual_override_invalidates_automatic_artwork(metadata):
    metadata.request = providers
    metadata.artist('10,000 Maniacs')
    with metadata.db.connect() as c:
        c.execute('INSERT INTO identities VALUES(?,?)', ('10,000 maniacs', OTHER))
    assert metadata.cached('10,000 Maniacs')[0] is None
    assert not metadata.cached_artwork(['10,000 Maniacs'])
    assert metadata.featured() is None


def test_photo_provider_failure_preserves_biography_and_retries(metadata):
    def response(url, params):
        if 'fanart.tv' in url:
            raise httpx.ConnectError('test outage')
        return providers(url, params)
    metadata.request = response
    data = metadata.artist('10,000 Maniacs')
    assert data['biography'].startswith('An American')
    assert data['images'] == []
    _, expires, _ = metadata.cached('10,000 Maniacs')
    assert expires < time.time() + 901


@pytest.mark.parametrize('lastfm_error', [6, 29])
def test_lastfm_missing_artist_or_rate_limit_does_not_block_fanart(metadata, monkeypatch, lastfm_error):
    original_client = httpx.Client
    def handler(request):
        url = str(request.url)
        if 'audioscrobbler' in url:
            return httpx.Response(200, json={'error': lastfm_error})
        return httpx.Response(200, json=providers(url.split('?')[0], {}))
    monkeypatch.setattr('mvideo.metadata.httpx.Client', lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs))
    data = metadata.artist('10,000 Maniacs')
    assert data['images'] == ['https://assets.fanart.tv/artist.jpg']
    assert data['biography'] is None
    if lastfm_error == 29:
        assert 'ws.audioscrobbler.com' in metadata.backoff_until
        assert 'webservice.fanart.tv' not in metadata.backoff_until


def test_background_lookup_returns_promptly_and_deduplicates(metadata):
    started, release = threading.Event(), threading.Event()
    calls = []
    def response(url, params):
        calls.append(url)
        if 'musicbrainz.org' in url:
            started.set()
            assert release.wait(5)
        return providers(url, params)
    metadata.request = response
    try:
        assert metadata.lookup('10,000 Maniacs')['pending'] is True
        assert started.wait(2)
        for _ in range(10):
            assert metadata.lookup('10,000 MANIACS')['pending'] is True
        assert len(calls) == 1
    finally:
        release.set()
    metadata.close()
    assert metadata.lookup('10,000 Maniacs')['images']
    assert len(calls) == 3
