import hashlib
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mvideo.api import create_app
from mvideo.config import Settings


@pytest.fixture
def service(tmp_path):
    root = tmp_path/'media'; root.mkdir()
    (root/'Band - Song (2000).mp4').write_bytes(b'x')
    app = create_app(Settings(root, tmp_path/'state', file_stability_seconds=0))
    app.state.library.probe = lambda path: {'format': {'duration': '10'}, 'streams': []}
    app.state.library.scan()
    token = app.state.auth.pair(app.state.auth.pair_code())
    with app.state.database.connect() as db:
        db.execute('INSERT INTO identities VALUES(?,?)', ('Band', 'verified'))
        db.execute('INSERT INTO metadata VALUES(?,?,?)', ('Band', json.dumps({
            'images': ['https://assets.fanart.tv/one.jpg', 'https://assets.fanart.tv/two.jpg'],
            'background_count': 2, 'mbid': 'verified', 'image_source_url': 'https://fanart.tv/artist/verified/'}), 9_999_999_999))
    yield app, TestClient(app), {'Authorization': 'Bearer '+token}, root
    app.state.playback.close()
    app.state.metadata.close()


def jpeg(size=(1920, 1080)):
    stream = io.BytesIO()
    Image.new('RGB', size, '#a35817').save(stream, format='JPEG')
    return stream.getvalue()


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr('mvideo.metadata.httpx.Client', lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs))


def test_image_buckets_preserve_expiry_resource_session_and_restart_scope(service, monkeypatch):
    app, _, headers, _ = service
    auth = app.state.auth
    sid = auth.authenticate(headers['Authorization'][7:])
    window = 4*3600
    now = 1_800_000_000//window*window+100
    monkeypatch.setattr('mvideo.auth.time.time', lambda: now)
    with auth.db.connect() as db:
        db.execute('UPDATE sessions SET expires=?', (now+90*86400,))
    first = auth.ticket(sid, 'image:one', cacheable=True)
    expiry = int(first.split('.')[1])
    assert now+window <= expiry < now+2*window
    monkeypatch.setattr('mvideo.auth.time.time', lambda: now+600)
    assert first == auth.ticket(sid, 'image:one', cacheable=True)
    assert auth.verify_ticket(first, 'image:one')
    assert not auth.verify_ticket(first, 'image:two')
    assert not auth.verify_ticket(first, 'media:one')
    assert int(auth.ticket(sid, 'media:one').split('.')[1]) == now+600+window
    monkeypatch.setattr('mvideo.auth.time.time', lambda: now//window*window+window)
    assert first != auth.ticket(sid, 'image:one', cacheable=True)
    assert auth.verify_ticket(first, 'image:one')
    monkeypatch.setattr('mvideo.auth.time.time', lambda: expiry)
    assert not auth.verify_ticket(first, 'image:one')
    monkeypatch.setattr('mvideo.auth.time.time', lambda: now)
    from mvideo.auth import Auth
    assert not Auth(auth.db).verify_ticket(first, 'image:one')
    with auth.db.connect() as db:
        db.execute('DELETE FROM sessions')
    assert not auth.verify_ticket(first, 'image:one')


def test_catalog_links_reuse_images_and_invalidate_replaced_content(service):
    app, client, headers, _ = service
    first = client.get('/api/videos', headers=headers).json()['items'][0]
    identity = first['id']
    for route in ('/api/videos', '/api/videos/'+identity):
        result = client.get(route, headers=headers).json()
        assert (result['items'][0] if 'items' in result else result)['thumbnail'] == first['thumbnail']
    for kind in ('artists', 'years', 'decades'):
        assert client.get('/api/facets/'+kind, headers=headers).json()['items'][0]['thumbnail'] == first['thumbnail']
    playlist = client.post('/api/playlists', headers=headers, json={
        'name': 'Mix', 'description': '', 'ids': [identity]}).json()
    assert playlist['thumbnail'] == first['thumbnail']
    old = app.state.library.get(identity)
    target = app.state.playback.settings.state/'thumbnails'/(app.state.playback.cache_key(old)+'.jpg')
    target.write_bytes(jpeg())
    assert client.get(first['thumbnail']).headers['cache-control'] == 'private, max-age=3600'
    with app.state.database.connect() as db:
        db.execute('UPDATE videos SET mtime=mtime+1 WHERE id=?', (identity,))
    changed = client.get('/api/videos', headers=headers).json()['items'][0]['thumbnail']
    assert changed != first['thumbnail']
    assert client.get(first['thumbnail']).status_code == 404
    token = app.state.auth.pair(app.state.auth.pair_code())
    other = client.get('/api/videos', headers={'Authorization': 'Bearer '+token}).json()['items'][0]['thumbnail']
    assert other != changed


def test_artwork_size_version_and_revocation(service, monkeypatch):
    app, client, headers, _ = service
    calls = []
    transport(monkeypatch, lambda request: (calls.append(str(request.url)), httpx.Response(
        200, content=jpeg(), headers={'Content-Type': 'image/jpeg'}))[1])
    first = client.get('/api/artist?name=Band', headers=headers).json()['images'][0]
    assert client.get('/api/artist?name=Band', headers=headers).json()['images'][0] == first
    assert client.get('/api/facets/artists', headers=headers).json()['items'][0]['image'] == first
    for width in (640, 1280, 1920):
        response = client.get(first+'&width='+str(width))
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'private, max-age=3600'
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.size == (width, round(width*9/16))
        assert client.get(first+'&width='+str(width)).content == response.content
    assert len(calls) == 1
    assert client.get(first+'&width=800').status_code == 422
    with app.state.database.connect() as db:
        row = db.execute('SELECT data FROM metadata').fetchone()
        data = json.loads(row[0]); data['images'].reverse()
        db.execute('UPDATE metadata SET data=?', (json.dumps(data),))
    assert client.get('/api/artist?name=Band', headers=headers).json()['images'][0] != first
    assert client.get(first+'&width=640').status_code == 404
    client.delete('/api/session', headers=headers)
    assert client.get(first+'&width=640').status_code == 401


def test_distinct_originals_download_concurrently(service, monkeypatch):
    app, _, _, _ = service
    barrier = threading.Barrier(2)
    def download(request):
        barrier.wait(timeout=3)
        return httpx.Response(200, content=jpeg(), headers={'Content-Type': 'image/jpeg'})
    transport(monkeypatch, download)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(app.state.metadata.image, 'Band', i, 640) for i in (0, 1)]
        assert all(future.result(timeout=5).exists() for future in futures)
    assert not app.state.metadata.image_locks


def test_same_original_coalesces_across_sizes(service, monkeypatch):
    app, _, _, _ = service
    started, release = threading.Event(), threading.Event()
    calls = []
    def download(request):
        calls.append(str(request.url)); started.set()
        assert release.wait(3)
        return httpx.Response(200, content=jpeg(), headers={'Content-Type': 'image/jpeg'})
    transport(monkeypatch, download)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(app.state.metadata.image, 'Band', 0, 640)
        assert started.wait(2)
        others = [pool.submit(app.state.metadata.image, 'Band', 0, width) for width in (640, 1280)]
        release.set()
        assert first.result(timeout=5) == others[0].result(timeout=5)
        assert others[1].result(timeout=5).exists()
    assert len(calls) == 1
    assert not app.state.metadata.image_locks
    assert not list((app.state.metadata.settings.state/'artwork').glob('*.partial'))


@pytest.mark.parametrize('content,content_type', [(b'invalid', 'image/jpeg'), (jpeg(), 'text/html'),
                                               (jpeg((5000, 4000)), 'image/jpeg'), (b'x'*(10*1024**2+1), 'image/jpeg')],
                         ids=['malformed', 'wrong-content-type', 'too-many-pixels', 'too-many-bytes'])
def test_invalid_artwork_does_not_poison_cache(service, monkeypatch, content, content_type):
    app, _, _, _ = service
    transport(monkeypatch, lambda request: httpx.Response(200, content=content, headers={'Content-Type': content_type}))
    with pytest.raises((OSError, ValueError)):
        app.state.metadata.image('Band', 0, 640)
    assert not list((app.state.metadata.settings.state/'artwork').iterdir())
    assert not app.state.metadata.image_locks


def test_small_artwork_is_not_enlarged_and_legacy_originals_are_reused(service, monkeypatch):
    app, _, _, _ = service
    key = hashlib.sha256(b'https://assets.fanart.tv/one.jpg').hexdigest()
    original = app.state.metadata.settings.state/'artwork'/(key+'.jpg')
    original.write_bytes(jpeg((320, 180)))
    transport(monkeypatch, lambda request: pytest.fail('Existing artwork must not download again'))
    with Image.open(app.state.metadata.image('Band', 0, 1280)) as image:
        assert image.size == (320, 180)
    assert app.state.metadata.image('Band', 0) == original
