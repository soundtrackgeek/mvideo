from contextlib import contextmanager
from dataclasses import replace
import json
import os
import sqlite3
import threading

import pytest

from mvideo.config import Settings
from mvideo.database import Database
from mvideo.library import Library


@pytest.fixture
def library(tmp_path):
    root = tmp_path/'media'
    root.mkdir()
    settings = Settings(root, tmp_path/'state', file_stability_seconds=0)
    settings.prepare()
    library = Library(settings, Database(settings.state/'library.sqlite3'))
    library.probe = lambda _: {'streams': [{'codec_type': 'audio', 'index': 1}]}
    return library


def jobs(library):
    with library.database.connect() as db:
        return {row['video_id']: (row['size'], row['mtime']) for row in db.execute('SELECT * FROM loudness_jobs')}


def test_unchanged_scan_uses_one_snapshot_connection(library, monkeypatch):
    for index in range(100):
        (library.settings.library/f'Artist - Song {index}.mp4').write_bytes(b'video')
    assert library.scan()['changed'] == 100
    connections, statements = [], []
    connect = library.database.connect

    @contextmanager
    def tracked_connect():
        connections.append(True)
        with connect() as db:
            db.set_trace_callback(statements.append)
            yield db

    monkeypatch.setattr(library.database, 'connect', tracked_connect)
    library.probe = lambda _: pytest.fail('Unchanged files must not be probed')
    result = library.scan()
    assert result['scanned'] == 100 and result['changed'] == result['deferred'] == 0
    assert len(connections) == 1
    assert sum('SELECT id,size,mtime,available,probe_error FROM videos' in sql for sql in statements) == 1
    assert not any('overrides' in sql for sql in statements)
    assert not any(sql.startswith(('INSERT', 'UPDATE', 'DELETE', 'BEGIN')) for sql in statements)


def test_candidates_share_wait_and_copying_files_are_deferred(library):
    stable = library.settings.library/'Artist - Stable.mp4'
    copying = library.settings.library/'Artist - Copying.mp4'
    stable.write_bytes(b'complete')
    copying.write_bytes(b'part')
    library.settings = replace(library.settings, file_stability_seconds=5)
    waits, probed = [], []

    class SettlingEvent:
        def is_set(self):
            return False

        def wait(self, timeout):
            assert not probed
            waits.append(timeout)
            copying.write_bytes(b'part two')
            return False

    library.probe = lambda path: probed.append(path) or {'streams': []}
    result = library.scan(stop_event=SettlingEvent())
    assert waits == [5]
    assert probed == [stable]
    assert result['changed'] == result['deferred'] == 1 and result['pending'] == 0
    assert [row['title'] for row in library.videos()['items']] == ['Stable']
    assert len(jobs(library)) == 1
    library.settings = replace(library.settings, file_stability_seconds=0)
    assert library.scan()['changed'] == 1
    assert len(jobs(library)) == 2


def test_file_changed_during_probe_keeps_previous_metadata(library):
    path = library.settings.library/'Artist - Song.mp4'
    path.write_bytes(b'original')
    library.scan()
    identity = library.ids()[0]
    original = dict(library.get(identity))
    revision, original_jobs = library.database.revision(), jobs(library)
    path.write_bytes(b'new file')

    def growing_probe(source):
        source.write_bytes(b'new file with more data')
        return {'streams': []}

    library.probe = growing_probe
    result = library.scan()
    assert result['changed'] == 0 and result['deferred'] == 1
    assert dict(library.get(identity)) == original
    assert library.database.revision() == revision and jobs(library) == original_jobs


def test_completed_probe_is_published_with_revision_and_exact_job(library):
    path = library.settings.library/'Artist - Song.mp4'
    path.write_bytes(b'complete')
    revision = library.database.revision()
    probe = {'streams': [{'codec_type': 'audio', 'index': 4}]}

    def inspect(source):
        assert library.ids() == []
        assert library.database.revision() == revision
        assert jobs(library) == {}
        return probe

    library.probe = inspect
    assert library.scan()['changed'] == 1
    identity = library.ids()[0]
    row = library.get(identity)
    assert json.loads(row['probe']) == probe and row['probe_error'] is None
    assert library.database.revision() == revision + 1
    assert jobs(library) == {identity: (path.stat().st_size, path.stat().st_mtime_ns)}


def test_reprobe_and_restored_files_are_queued(library):
    path = library.settings.library/'Artist - Song.mp4'
    path.write_bytes(b'complete')
    library.scan()
    identity = library.ids()[0]
    with library.database.connect() as db:
        db.execute('DELETE FROM loudness_jobs')
        db.execute("UPDATE videos SET probe_error='Retry' WHERE id=?", (identity,))
        db.execute('INSERT INTO overrides VALUES(?,?,?,?)', (identity, 'Edited artist', 'Edited title', 2000))
    revision = library.database.revision()
    assert library.scan()['changed'] == 1
    assert identity in jobs(library)
    row = library.get(identity)
    assert (row['artist'], row['title'], row['year']) == ('Edited artist', 'Edited title', 2000)
    assert row['probe_error'] is None and library.database.revision() == revision + 1
    source_stat = path.stat()
    path.unlink()
    assert library.scan()['missing'] == 1
    assert library.database.revision() == revision + 2
    with library.database.connect() as db:
        db.execute('DELETE FROM loudness_jobs')
    path.write_bytes(b'complete')
    os.utime(path, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    assert library.scan()['changed'] == 1
    assert identity in jobs(library) and library.get(identity)['available'] == 1


def test_cancelled_settling_retains_catalog_and_releases_lock(library):
    path = library.settings.library/'Artist - Existing.mp4'
    path.write_bytes(b'existing')
    library.scan()
    path.unlink()
    (library.settings.library/'Artist - New.mp4').write_bytes(b'new')
    stop = threading.Event()

    def cancel(timeout):
        stop.set()
        return True

    stop.wait = cancel
    result = library.scan(stop_event=stop)
    assert result['state'] == 'stopped' and result['deferred'] == 1
    assert result['changed'] == result['missing'] == result['pending'] == 0
    assert [row['title'] for row in library.videos()['items']] == ['Existing']
    assert not library.scan_lock.locked()
    result = library.scan()
    assert result['state'] == 'idle' and result['missing'] == result['changed'] == 1


def test_catalog_and_loudness_job_commit_atomically(library):
    (library.settings.library/'Artist - Song.mp4').write_bytes(b'complete')
    with library.database.connect() as db:
        db.execute("""CREATE TRIGGER reject_loudness_job BEFORE INSERT ON loudness_jobs
                      BEGIN SELECT RAISE(ABORT, 'Cannot enqueue'); END""")
    revision = library.database.revision()
    with pytest.raises(sqlite3.IntegrityError, match='Cannot enqueue'):
        library.scan()
    assert library.ids() == [] and jobs(library) == {}
    assert library.database.revision() == revision
    assert not library.scan_lock.locked()


def test_candidate_is_rechecked_after_another_probe(library):
    paths = [library.settings.library/f'Artist - Song {index}.mp4' for index in range(2)]
    for path in paths:
        path.write_bytes(b'complete')
    probed = []

    def inspect(source):
        probed.append(source)
        next(path for path in paths if path != source).write_bytes(b'replacement')
        return {'streams': []}

    library.probe = inspect
    result = library.scan()
    assert len(probed) == 1
    assert result['changed'] == result['deferred'] == 1


def test_override_saved_during_probe_remains_visible(library):
    path = library.settings.library/'Artist - Song.mp4'
    path.write_bytes(b'complete')
    library.scan()
    identity = library.ids()[0]
    path.write_bytes(b'replacement')

    def inspect(source):
        with library.database.connect() as db:
            db.execute('INSERT INTO overrides VALUES(?,?,?,?)', (identity, 'Updated artist', 'Updated title', 2001))
            db.execute('UPDATE videos SET artist=?,title=?,year=?,warnings=? WHERE id=?',
                       ('Updated artist', 'Updated title', 2001, '[]', identity))
            library._index(db, identity, {'artist': 'Updated artist', 'title': 'Updated title', 'year': 2001})
            db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
        return {'streams': []}

    library.probe = inspect
    assert library.scan()['changed'] == 1
    row = library.get(identity)
    assert (row['artist'], row['title'], row['year'], row['warnings']) == ('Updated artist', 'Updated title', 2001, '[]')
    assert library.videos(q='Updated title')['total'] == 1
    assert library.scan()['changed'] == 0


def test_concurrent_scan_returns_busy_without_overwriting_active_status(library):
    library.scan_status = {'state': 'probing', 'scanned': 2, 'changed': 1, 'deferred': 0}
    with library.scan_lock:
        assert library.scan()['state'] == 'busy'
        assert library.scan_status['state'] == 'probing'
