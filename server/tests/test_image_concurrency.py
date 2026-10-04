import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading

import anyio
import httpx
import pytest

from mvideo.api import create_app
from mvideo.config import Settings


@pytest.fixture
def image_service(tmp_path):
    root = tmp_path/'media'; root.mkdir()
    (root/'Band - Song (2000).mp4').write_bytes(b'x')
    app = create_app(Settings(root, tmp_path/'state', file_stability_seconds=0))
    app.state.library.probe = lambda path: {'format': {'duration': '10'}, 'streams': []}
    app.state.library.scan()
    token = app.state.auth.pair(app.state.auth.pair_code())
    yield app, token
    app.state.playback.close()
    app.state.metadata.close()


@pytest.mark.parametrize('kind', ['thumbnail', 'artwork'])
def test_slow_images_leave_catalog_and_shuffle_responsive(image_service, tmp_path, monkeypatch, kind):
    app, token = image_service
    sid = app.state.auth.authenticate(token)
    identity = app.state.library.ids()[0]
    target = tmp_path/'image.jpg'; target.write_bytes(b'jpeg')
    release = threading.Event()
    occupied = threading.Event()
    lock = threading.Lock()
    started = 0

    def slow_image(*args):
        nonlocal started
        with lock:
            started += 1
            if started == 2:
                occupied.set()
        assert release.wait(5), 'The test did not release image loading'
        return target

    if kind == 'thumbnail':
        monkeypatch.setattr(app.state.playback, 'thumbnail', slow_image)
        path = '/image/'+identity+'/'+app.state.auth.ticket(sid, 'image:'+identity)
    else:
        monkeypatch.setattr(app.state.metadata, 'image', slow_image)
        key = hashlib.sha256(b'Band').hexdigest()
        path = '/artwork/'+key+'/0/'+app.state.auth.ticket(sid, 'artwork:'+key+':0')+'?name=Band'

    async def scenario():
        # Two ordinary request workers make saturation deterministic without
        # starting forty threads. A real Home grid can issue 48 image requests.
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        limiter.total_tokens = 2
        requests = []
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test',
                                        headers={'Authorization': 'Bearer '+token}) as client:
                requests = [asyncio.create_task(client.get(path)) for _ in range(48)]
                try:
                    assert await asyncio.to_thread(occupied.wait, 2), 'Image requests never started'
                    catalog = await asyncio.wait_for(client.get('/api/videos'), 1)
                    assert catalog.status_code == 200
                    assert catalog.json()['total'] == 1
                    queue = await asyncio.wait_for(client.post('/api/queue', json={'shuffle': True}), 1)
                    assert queue.status_code == 200
                    assert queue.json()['ids'] == [identity]
                    assert not release.is_set(), 'Library requests must finish before the images'
                finally:
                    release.set()
                    results = await asyncio.gather(*requests)
                assert all(response.status_code == 200 for response in results)
        finally:
            release.set()
            limiter.total_tokens = previous

    asyncio.run(scenario())


def test_cached_thumbnail_does_not_wait_for_another_extraction(image_service):
    app, _ = image_service
    playback = app.state.playback
    identity = app.state.library.ids()[0]
    target = playback.settings.state/'thumbnails'/(playback.cache_key(app.state.library.get(identity))+'.jpg')
    target.write_bytes(b'cached')
    with ThreadPoolExecutor(max_workers=1) as pool:
        playback.thumbnail_lock.acquire()
        try:
            result = pool.submit(playback.thumbnail, identity)
            assert result.result(timeout=1) == target
        finally:
            playback.thumbnail_lock.release()
