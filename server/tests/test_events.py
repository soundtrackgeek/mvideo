import asyncio
import json
import threading
import socket
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from mvideo.api import create_app
from mvideo.config import Settings


@pytest.fixture
def service(tmp_path):
    root = tmp_path/'media'
    root.mkdir()
    app = create_app(Settings(root, tmp_path/'state', file_stability_seconds=0), scan_interval=0)
    app.state.library.probe = lambda path: {}
    token = app.state.auth.pair(app.state.auth.pair_code())
    yield app, root, token
    app.state.playback.close()
    app.state.metadata.close()


def test_events_require_pairing_and_facets_detect_stale_revision(service):
    app, root, token = service
    client = TestClient(app)
    assert client.get('/api/events').status_code == 401
    headers = {'Authorization': 'Bearer '+token}
    (root/'Band - One (2000).mp4').write_bytes(b'x')
    app.state.library.scan()
    first = client.get('/api/facets/artists', headers=headers).json()
    assert first['revision'] == app.state.database.revision()
    (root/'Band - Two (2001).mp4').write_bytes(b'x')
    app.state.library.scan()
    assert client.get('/api/facets/artists', params={'revision': first['revision']}, headers=headers).status_code == 409


def test_stream_catches_cli_changes_replacements_removals_and_artwork(service):
    app, root, token = service
    async def verify():
        stream = app.state.events.stream(app.state.auth.authenticate(token), interval=0.001)
        try:
            first = await anext(stream)
            assert first.event == 'snapshot' and first.data == {'revision': 0, 'total': 0}
            media = root/'Band - One (2000).mp4'
            media.write_bytes(b'x')
            # A separate Library instance represents an out-of-process CLI scan.
            from mvideo.library import Library
            scanner = Library(app.state.library.settings, app.state.database)
            scanner.probe = lambda path: {}
            scanner.scan()
            added = await anext(stream)
            assert added.event == 'library-changed' and added.data == {'revision': 1, 'total': 1}
            media.write_bytes(b'changed')
            scanner.scan()
            replaced = await anext(stream)
            assert replaced.data == {'revision': 2, 'total': 1}
            media.unlink()
            scanner.scan()
            removed = await anext(stream)
            assert removed.data == {'revision': 3, 'total': 0}
            app.state.events.artwork_ready('Band')
            ready = await anext(stream)
            assert ready.event == 'artwork-ready' and ready.data['artist'] == 'Band'
            # No event for an unchanged catalog; cancellation releases the stream.
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(anext(stream), timeout=0.02)
        finally:
            await stream.aclose()
    asyncio.run(verify())


def test_slow_subscriber_resynchronizes_and_revoked_session_ends_stream(service):
    app, _, token = service
    async def verify():
        sid = app.state.auth.authenticate(token)
        stream = app.state.events.stream(sid, interval=0.001)
        await anext(stream)
        for i in range(150):
            app.state.events.artwork_ready('Artist '+str(i))
        recovered = await anext(stream)
        assert recovered.event == 'snapshot'
        with app.state.database.connect() as db:
            db.execute('DELETE FROM sessions WHERE hash=?', (sid,))
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    asyncio.run(verify())


def test_artwork_completion_is_published_after_pending_job_is_cleared(service):
    app, _, _ = service
    metadata = app.state.metadata
    metadata.pending.add('band')
    metadata.artist = lambda name: {'images': []}
    calls = []
    metadata.on_ready = lambda name: calls.append((name, set(metadata.pending)))
    metadata._load('Band', 'band')
    assert calls == [('Band', set())]
    metadata.artist = lambda name: (_ for _ in ()).throw(RuntimeError('provider failed'))
    with pytest.raises(RuntimeError):
        metadata._load('Band', 'band')
    assert len(calls) == 1


def test_full_artwork_queue_reports_deferral_until_a_completion_frees_a_slot(service):
    app, _, _ = service
    metadata = app.state.metadata
    metadata.pending.update('artist-'+str(i) for i in range(64))
    assert metadata.lookup('Waiting')['deferred'] is True
    assert 'waiting' not in metadata.pending
    metadata.pending.remove('artist-0')
    started = threading.Event()
    finish = threading.Event()
    def artist(name):
        started.set()
        assert finish.wait(timeout=3)
        return {'images': []}
    metadata.artist = artist
    try:
        assert metadata.lookup('Waiting')['deferred'] is False
        assert started.wait(timeout=3)
        assert 'waiting' in metadata.pending
    finally:
        finish.set()


def test_live_http_stream_delivers_frames_and_stops_on_revocation(service):
    app, root, token = service
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, lifespan='off', log_level='error'))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic()+5
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=8) as client:
            with client.stream('GET', '/api/events', headers={'Authorization': 'Bearer '+token}) as response:
                assert response.status_code == 200
                assert response.headers['content-type'].startswith('text/event-stream')
                assert 'no-transform' in response.headers['cache-control']
                assert response.headers['x-accel-buffering'] == 'no'
                lines = response.iter_lines()
                assert next(lines) == 'event: snapshot'
                assert next(lines).startswith('data: ')
                assert next(lines) == ''
                (root/'Band - Song (2000).mp4').write_bytes(b'x')
                app.state.library.scan()
                assert next(lines) == 'event: library-changed'
                assert json.loads(next(lines).removeprefix('data: '))['total'] == 1
                assert next(lines) == ''
                app.state.events.artwork_ready('Band')
                assert next(lines) == 'event: artwork-ready'
                assert 'Band' in next(lines)
                assert next(lines) == ''
                sid = app.state.auth.authenticate(token)
                with app.state.database.connect() as db:
                    db.execute('DELETE FROM sessions WHERE hash=?', (sid,))
                assert list(lines) == []
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        assert not worker.is_alive()
