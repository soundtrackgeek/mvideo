from dataclasses import replace
import os
import threading
import time
import sys

from fastapi.testclient import TestClient
import pytest
from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent, FileOpenedEvent
from watchdog.utils.dirsnapshot import DirectorySnapshot

from mvideo.api import create_app
from mvideo.cli import main
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.ingestion import Ingestion, LibraryEvents, watch_entries
from mvideo.library import Library
from mvideo.loudness import scan_lock


@pytest.fixture
def ingestion(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    settings = Settings(root, tmp_path / 'state', watch_mode='off', file_stability_seconds=0)
    settings.prepare()
    database = Database(settings.state / 'library.sqlite3')
    library = Library(settings, database)
    library.probe = lambda _: {'streams': [{'codec_type': 'audio', 'index': 1}]}
    worker = Ingestion(settings, database, library, scan_interval=0)
    yield worker
    worker.close()


def add(worker, name):
    path = worker.settings.library / f'Band - {name} (2000).mp4'
    path.write_bytes(b'audio')
    worker.library.scan()
    return worker.library.videos(q=name)['items'][0]['id']


def fake_analysis(worker, monkeypatch):
    calls = []
    monkeypatch.setattr(worker.scanner, 'preflight', lambda: None)
    def measure(path, row, timeout, **kwargs):
        calls.append(row['id'])
        return {'status': 'measured', 'integrated_lufs': -20, 'true_peak_dbtp': -5,
                'loudness_range_lu': 1, 'threshold_lufs': -30}
    monkeypatch.setattr(worker.scanner, 'measure', measure)
    return calls


def eventually(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        threading.Event().wait(.01)
    assert predicate()


def test_only_changed_ids_are_measured_and_cli_jobs_survive_restart(ingestion, monkeypatch):
    first = add(ingestion, 'First')
    calls = fake_analysis(ingestion, monkeypatch)
    assert ingestion._measure_next()
    assert calls == [first]
    second = add(ingestion, 'Second')
    # A fresh service instance picks up the IDs persisted by an independent scan.
    resumed = Ingestion(ingestion.settings, ingestion.database, ingestion.library, scan_interval=0)
    calls = fake_analysis(resumed, monkeypatch)
    assert resumed._measure_next()
    assert calls == [second]
    assert not resumed._measure_next()
    assert resumed.status()['pending_loudness'] == 0
    assert resumed.scanner.status()['measured'] == 2


def test_bulk_lock_preserves_pending_jobs(ingestion, monkeypatch):
    add(ingestion, 'Song')
    calls = fake_analysis(ingestion, monkeypatch)
    with scan_lock(ingestion.settings.state / 'loudness.lock'):
        with pytest.raises(RuntimeError, match='Another loudness scan'):
            ingestion._measure_next()
    assert calls == []
    assert ingestion.status()['pending_loudness'] == 1
    assert ingestion._measure_next()
    assert len(calls) == 1


def test_newer_job_is_not_deleted_by_completed_measurement(ingestion, monkeypatch):
    identity = add(ingestion, 'Song')
    def run(**kwargs):
        with ingestion.database.connect() as db:
            db.execute('UPDATE loudness_jobs SET mtime=mtime+1 WHERE video_id=?', (identity,))
        return {'state': 'finished', 'error': 0, 'deferred': 0}
    monkeypatch.setattr(ingestion.scanner, 'run', run)
    assert ingestion._measure_next()
    assert ingestion.status()['pending_loudness'] == 1


def test_cancellation_keeps_job_and_shutdown_stops_workers(ingestion, monkeypatch):
    add(ingestion, 'Song')
    entered = threading.Event()
    def run(*, ids, stop_event):
        entered.set()
        assert stop_event.wait(5)
        return {'state': 'cancelled'}
    monkeypatch.setattr(ingestion.scanner, 'run', run)
    ingestion.start()
    assert entered.wait(5)
    threads = list(ingestion.threads)
    ingestion.close()
    assert not any(thread.is_alive() for thread in threads)
    assert ingestion.status()['pending_loudness'] == 1


def test_errors_complete_jobs_and_missing_videos_are_discarded(ingestion, monkeypatch):
    identity = add(ingestion, 'First')
    add(ingestion, 'Second')
    fake_analysis(ingestion, monkeypatch)
    def broken(*args, **kwargs):
        raise ValueError('Bad audio')
    monkeypatch.setattr(ingestion.scanner, 'measure', broken)
    assert ingestion._measure_next()
    assert ingestion.scanner.status()['error'] == 1
    with ingestion.database.connect() as db:
        db.execute('UPDATE videos SET available=0 WHERE id!=?', (identity,))
    assert ingestion._measure_next()
    assert ingestion.status()['pending_loudness'] == 0


def test_watcher_filters_reads_and_recognizes_moves():
    calls = []
    events = LibraryEvents(lambda **kwargs: calls.append(kwargs))
    events.on_any_event(FileOpenedEvent('song.mp4'))
    events.on_any_event(FileModifiedEvent('notes.txt'))
    assert calls == []
    events.on_any_event(FileCreatedEvent('song.MP4'))
    events.on_any_event(FileMovedEvent('copy.tmp', 'song.mkv'))
    assert calls == [{'delay': 5}, {'delay': 5}]


def test_scan_requests_coalesce_without_starving_or_losing_new_events(ingestion, monkeypatch):
    monkeypatch.setattr('mvideo.ingestion.time.monotonic', lambda: 10)
    ingestion.request_scan(delay=5)
    monkeypatch.setattr('mvideo.ingestion.time.monotonic', lambda: 12)
    ingestion.request_scan(delay=5)
    assert ingestion.scan_due == 15
    ingestion.request_scan()
    assert ingestion.scan_due == 12


def test_scan_retries_deferred_files(ingestion, monkeypatch):
    scanned = threading.Event()
    def scan(**kwargs):
        scanned.set()
        return {'state': 'idle', 'deferred': 1}
    monkeypatch.setattr(ingestion.library, 'scan', scan)
    ingestion.request_scan()
    ingestion.start()
    assert scanned.wait(5)
    eventually(lambda: ingestion.scan_due is not None)
    assert ingestion.scan_due > time.monotonic()


def test_polling_observer_detects_new_file_and_measures_it(ingestion, monkeypatch):
    ingestion.settings = replace(ingestion.settings, watch_mode='polling', watch_interval=.05)
    calls = fake_analysis(ingestion, monkeypatch)
    original_request = ingestion.request_scan
    monkeypatch.setattr(ingestion, 'request_scan', lambda **kwargs: original_request())
    ingestion.start()
    eventually(lambda: ingestion.watcher_status['state'] == 'watching')
    (ingestion.settings.library / 'Band - New (2000).mp4').write_bytes(b'audio')
    eventually(lambda: ingestion.scanner.status()['measured'] == 1)
    assert len(calls) == 1
    eventually(lambda: ingestion.status()['pending_loudness'] == 0)


def test_watcher_failure_keeps_periodic_scans_and_recovers(ingestion, monkeypatch):
    ingestion.settings = replace(ingestion.settings, watch_mode='polling')
    root = ingestion.settings.library
    root.rename(root.with_name('offline'))
    ingestion._watch()
    assert ingestion.watcher_status['state'] == 'retrying'
    assert ingestion.observer is None
    root.with_name('offline').rename(root)
    ingestion._watch()
    try:
        assert ingestion.watcher_status['state'] == 'watching'
        assert ingestion.scan_due is not None
        ingestion.observer.stop()
        ingestion.observer.join()
        ingestion._watch()
        assert ingestion.observer.is_alive()
    finally:
        ingestion._stop_observer()


def test_periodic_scan_continues_when_watcher_cannot_start(ingestion, monkeypatch):
    ingestion.settings = replace(ingestion.settings, watch_mode='polling')
    ingestion.scan_interval = .05
    scanned = []
    def unavailable(*args, **kwargs):
        raise OSError('Watch unavailable')
    monkeypatch.setattr('mvideo.ingestion.PollingObserverVFS.schedule', unavailable)
    monkeypatch.setattr(ingestion.library, 'scan', lambda **kwargs: scanned.append(True) or {'state': 'idle'})
    ingestion.start()
    eventually(lambda: len(scanned) >= 2)
    assert ingestion.watcher_status['state'] == 'retrying'


def test_polling_does_not_traverse_links_or_junctions(ingestion, monkeypatch, tmp_path):
    root = ingestion.settings.library
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'Band - Outside (2000).mp4').write_bytes(b'audio')
    (root / 'linked').symlink_to(outside, target_is_directory=True)
    (root / 'cycle').symlink_to(root, target_is_directory=True)
    (root / 'Band - Linked (2000).mp4').symlink_to(outside / 'Band - Outside (2000).mp4')
    (root / 'junction').mkdir()
    (root / 'junction' / 'Band - Other (2000).mp4').write_bytes(b'audio')
    (root / 'notes.txt').write_text('ignored')
    (root / 'Band - Local (2000).mp4').write_bytes(b'audio')
    monkeypatch.setattr(type(root), 'is_junction', lambda path: path.name == 'junction')
    snapshot = DirectorySnapshot(str(root), stat=os.lstat, listdir=watch_entries)
    assert snapshot.paths == {str(root), str(root / 'Band - Local (2000).mp4')}


@pytest.mark.parametrize(('arguments', 'interval', 'mode'), [
    ([], 1800, 'polling'), (['--scan-interval', '0', '--watch-mode', 'off'], 0, 'off'),
])
def test_serve_uses_lifespan_scheduler_and_cli_overrides(ingestion, monkeypatch, arguments, interval, mode):
    monkeypatch.setenv('MVIDEO_LIBRARY', str(ingestion.settings.library))
    monkeypatch.setenv('MVIDEO_STATE', str(ingestion.settings.state))
    monkeypatch.setenv('MVIDEO_WATCH_MODE', 'polling')
    monkeypatch.setattr(sys, 'argv', ['mvideo', 'serve', *arguments])
    called = []
    def serve(app, **kwargs):
        called.append(True)
        assert app.state.ingestion.scan_interval == interval
        assert app.state.ingestion.settings.watch_mode == mode
        assert app.state.ingestion.threads == []
        app.state.playback.close()
        app.state.metadata.close()
    monkeypatch.setattr('uvicorn.run', serve)
    main()
    assert called == [True]


def test_serve_rejects_too_short_scan_interval(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['mvideo', 'serve', '--scan-interval', '1'])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_api_status_scan_auth_and_lifespan(tmp_path, monkeypatch):
    root = tmp_path / 'media'
    root.mkdir()
    settings = Settings(root, tmp_path / 'state', watch_mode='off', file_stability_seconds=0)
    app = create_app(settings, scan_interval=0)
    app.state.library.probe = lambda _: {'streams': []}
    monkeypatch.setattr(app.state.ingestion.scanner, 'preflight', lambda: None)
    (root / 'Band - Silent (2000).mp4').write_bytes(b'video')
    with TestClient(app) as client:
        assert client.get('/api/status').status_code == 401
        assert client.post('/api/scan').status_code == 401
        token = client.post('/api/pair', json={'code': app.state.auth.pair_code()}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        assert client.post('/api/scan', headers=headers).json() == {'state': 'requested'}
        eventually(lambda: app.state.ingestion.scanner.status()['no_audio'] == 1)
        status = client.get('/api/status', headers=headers).json()
        assert status['total'] == 1
        assert status['loudness']['no_audio'] == 1
        assert status['ingestion']['watcher'] == {'mode': 'off', 'state': 'off'}
    assert app.state.ingestion.threads == []


@pytest.mark.parametrize('values', [
    {'watch_mode': 'bad'}, {'watch_interval': 0}, {'watch_interval': float('nan')},
    {'file_stability_seconds': -1}, {'file_stability_seconds': float('inf')},
])
def test_invalid_ingestion_settings(tmp_path, values):
    with pytest.raises(ValueError):
        Settings(tmp_path / 'media', tmp_path / 'state', **values).prepare()
