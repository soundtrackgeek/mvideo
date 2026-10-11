import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading

import pytest

from mvideo.config import Settings
from mvideo.content import SAMPLE_BYTES, content_key
from mvideo.database import Database
from mvideo.filenames import FilenameRepair
from mvideo.library import Library
from mvideo.loudness import ANALYSIS_VERSION, LoudnessScanner
import mvideo.library as library_module

PROBE = {'format': {'duration': '120.000000'}, 'streams': [{'codec_type': 'audio', 'index': 1}]}


@pytest.fixture
def library(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    settings = Settings(root, tmp_path / 'state', file_stability_seconds=0)
    settings.prepare()
    library = Library(settings, Database(settings.state / 'library.sqlite3'))
    library.probe = lambda _: PROBE
    return library


def seed(library, name='Band - Original (2000).mp4', data=b'original media'):
    path = library.settings.library / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    library.scan()
    with library.database.connect() as db:
        return path, dict(db.execute('SELECT * FROM videos WHERE path=?', (name,)).fetchone())


def references(library, row, *, stale=False):
    with library.database.connect() as db:
        db.execute("INSERT INTO playlists VALUES('mix','Mix','',1,0,0)")
        db.execute("INSERT INTO playlist_items VALUES('mix',?,0)", (row['id'],))
        db.execute('INSERT INTO overrides VALUES(?,?,?,?)', (row['id'], 'User artist', 'User title', 2002))
        db.execute("""INSERT INTO audio_loudness VALUES(?,?,?,?,'measured',-20,-4,5,-30,1,'test',1,NULL)""",
                   (row['id'], row['size'], row['mtime'] - int(stale), ANALYSIS_VERSION))
        db.execute('DELETE FROM loudness_jobs')


@pytest.mark.parametrize('copy_move', [False, True])
def test_rename_move_and_repeat_preserve_identity_and_dependents(library, caplog, copy_move):
    source, old = seed(library)
    references(library, old)
    target = source.parent / 'Pop' / 'Band - Renamed (2001).mp4'
    target.parent.mkdir()
    if copy_move:
        shutil.copyfile(source, target)
        os.utime(target, ns=(old['mtime'] + 1000000, old['mtime'] + 1000000))
        source.unlink()
    else:
        source.rename(target)
    revision = library.database.revision()
    with caplog.at_level('INFO', logger='mvideo.library'):
        result = library.scan()
    assert result['moved'] == result['changed'] == 1 and result['missing'] == 0
    assert library.ids() == [old['id']]
    assert library.source(old['id']) == target
    assert target.read_bytes() == b'original media'
    row = library.get(old['id'])
    assert (row['artist'], row['title'], row['year'], row['warnings']) == ('User artist', 'User title', 2002, '[]')
    assert row['content_key'] == old['content_key']
    assert library.videos(q='User title')['total'] == 1
    assert library.database.revision() == revision + 1
    assert 'Video moved' in caplog.text
    with library.database.connect() as db:
        assert db.execute('SELECT count(*) FROM videos').fetchone()[0] == 1
        assert db.execute('SELECT video_id FROM playlist_items').fetchone()[0] == old['id']
        assert db.execute('SELECT version FROM playlists').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM loudness_jobs').fetchone()[0] == 0
        assert db.execute('SELECT id FROM overrides').fetchone()[0] == old['id']
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert LoudnessScanner(library.settings, library.database).status()['measured'] == 1
    again = target.with_name('Band - Again (2003).mp4')
    target.rename(again)
    assert library.scan()['moved'] == 1
    assert library.source(old['id']) == again
    assert library.scan()['changed'] == 0


def test_new_filename_metadata_replaces_search_without_override(library):
    source, old = seed(library)
    target = source.with_name('New artist - New title (2004).mp4')
    source.rename(target)
    assert library.scan()['moved'] == 1
    row = library.get(old['id'])
    assert (row['artist'], row['title'], row['year']) == ('New artist', 'New title', 2004)
    assert library.videos(q='Original')['total'] == 0
    assert library.videos(q='New title')['items'][0]['id'] == old['id']


def test_case_only_rename_retains_id_on_case_insensitive_filesystems(library):
    source, old = seed(library)
    target = source.with_name(source.name.lower())
    source.rename(target)
    assert library.scan()['moved'] == 1
    assert library.get(old['id'])['path'] == target.name
    assert library.ids() == [old['id']]


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_real_media_rename_retains_measured_gain_and_source(library):
    source = library.settings.library / 'Band - Real (2000).mkv'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=32x32:r=1:d=2',
                    '-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=48000:duration=2',
                    '-map', '0:v', '-map', '1:a', '-t', '2', '-c:v', 'ffv1', '-c:a', 'pcm_s16le',
                    str(source)], check=True, capture_output=True)
    library.probe = Library.probe.__get__(library)
    assert library.scan()['changed'] == 1
    identity = library.ids()[0]
    scanner = LoudnessScanner(library.settings, library.database)
    assert scanner.run()['measured'] == 1
    original = hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns
    with library.database.connect() as db:
        db.execute('DELETE FROM loudness_jobs')
        measurement = dict(db.execute('SELECT * FROM audio_loudness').fetchone())
    target = source.with_name('Band - Real renamed (2001).mkv')
    source.rename(target)
    assert library.scan()['moved'] == 1
    assert library.source(identity) == target
    assert scanner.run()['cached'] == 1
    with library.database.connect() as db:
        assert dict(db.execute('SELECT * FROM audio_loudness').fetchone()) == measurement
        assert db.execute('SELECT count(*) FROM loudness_jobs').fetchone()[0] == 0
    assert (hashlib.sha256(target.read_bytes()).digest(), target.stat().st_mtime_ns) == original


def test_split_scan_move_and_reusing_original_path(library):
    source, old = seed(library)
    outside = source.parent.parent / 'temporary.mp4'
    source.rename(outside)
    assert library.scan()['missing'] == 1
    target = source.with_name('Band - Returned (2000).mp4')
    outside.rename(target)
    assert library.scan()['moved'] == 1
    source.write_bytes(b'completely different media')
    assert library.scan()['changed'] == 1
    assert library.source(old['id']) == target
    assert len(library.ids()) == 2
    with library.database.connect() as db:
        assert db.execute('SELECT id FROM videos WHERE path=?', (source.name,)).fetchone()[0] != old['id']


def test_source_reappearing_after_walk_is_a_separate_copy(library):
    source, old = seed(library)
    target = source.with_name('Band - New (2000).mp4')
    source.rename(target)

    def inspect(_):
        shutil.copyfile(target, source)
        return PROBE

    library.probe = inspect
    result = library.scan()
    assert result['moved'] == result['missing'] == 0
    assert library.source(old['id']) == source
    assert len(library.ids()) == 2


@pytest.mark.parametrize('scenario', ['present_copy', 'two_missing', 'two_incoming', 'different_bytes', 'different_duration'])
def test_ambiguous_or_nonmatching_files_never_inherit_references(library, scenario):
    source, old = seed(library)
    references(library, old)
    if scenario == 'two_missing':
        second, _ = seed(library, 'Band - Copy (2000).mp4')
        second.unlink()
    target = source.with_name('Band - New (2000).mp4')
    shutil.copyfile(source, target)
    if scenario != 'present_copy':
        source.unlink()
    if scenario == 'two_incoming':
        shutil.copyfile(target, source.with_name('Band - Second (2000).mp4'))
    if scenario == 'different_bytes':
        target.write_bytes(b'different data')  # Same size, different sample.
    if scenario == 'different_duration':
        library.probe = lambda _: dict(PROBE, format={'duration': '121'})
    assert library.scan()['moved'] == 0
    with library.database.connect() as db:
        new_id = db.execute('SELECT id FROM videos WHERE path=?', (target.name,)).fetchone()[0]
        assert new_id != old['id']
        assert db.execute('SELECT video_id FROM playlist_items').fetchone()[0] == old['id']
        assert db.execute('SELECT video_id FROM audio_loudness').fetchone()[0] == old['id']


def test_partial_walk_defers_matching_move_until_full_scan(library, monkeypatch):
    source, old = seed(library)
    unreadable = source.parent / 'inaccessible'
    unreadable.mkdir()
    target = source.with_name('Band - New (2000).mp4')
    source.rename(target)
    scandir = os.scandir

    def partial(path):
        if Path(path) == unreadable:
            raise PermissionError('Unavailable directory')
        return scandir(path)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'scandir', partial)
        result = library.scan()
        assert result['state'] == 'warning' and result['deferred'] == 1
        assert result['moved'] == result['changed'] == result['missing'] == 0
    assert library.scan()['moved'] == 1
    assert library.source(old['id']) == target


def test_upgrade_backfills_without_reprobe_revision_or_loudness_jobs(library):
    source, old = seed(library)
    references(library, old)
    with library.database.connect() as db:
        db.execute('DROP INDEX videos_content_key')
        db.execute('ALTER TABLE videos DROP COLUMN content_key')
    revision = library.database.revision()
    library.database = Database(library.database.path)
    library.probe = lambda _: pytest.fail('Backfill should use the saved duration')
    result = library.scan()
    assert result['fingerprinted'] == 1 and result['changed'] == 0
    assert library.get(old['id'])['content_key'] == old['content_key']
    assert library.database.revision() == revision
    with library.database.connect() as db:
        assert db.execute('SELECT count(*) FROM loudness_jobs').fetchone()[0] == 0
        assert db.execute('SELECT version FROM playlists').fetchone()[0] == 1
    library.probe = lambda _: PROBE
    source.rename(source.with_name('Band - Upgraded (2000).mp4'))
    assert library.scan()['moved'] == 1
    assert library.ids() == [old['id']]


def test_current_measurement_and_pending_job_stamps_follow_copy_move(library):
    source, old = seed(library)
    references(library, old, stale=True)
    with library.database.connect() as db:
        db.execute('INSERT INTO loudness_jobs VALUES(?,?,?)', (old['id'], old['size'], old['mtime']))
    target = source.with_name('Band - Copied (2000).mp4')
    shutil.copyfile(source, target)
    os.utime(target, ns=(old['mtime'] + 1000000, old['mtime'] + 1000000))
    source.unlink()
    assert library.scan()['moved'] == 1
    with library.database.connect() as db:
        assert db.execute('SELECT source_mtime FROM audio_loudness').fetchone()[0] == old['mtime'] - 1
        assert tuple(db.execute('SELECT size,mtime FROM loudness_jobs').fetchone()) == (target.stat().st_size, target.stat().st_mtime_ns)
    assert LoudnessScanner(library.settings, library.database).status()['stale'] == 1


def test_read_failure_or_changed_sample_never_publishes_move(library, monkeypatch):
    source, old = seed(library)
    target = source.with_name('Band - New (2000).mp4')
    source.rename(target)
    def failed_read(*_):
        raise PermissionError('Cannot sample')

    monkeypatch.setattr(library_module, 'content_key', failed_read)
    assert library.scan()['deferred'] == 1
    with library.database.connect() as db:
        assert db.execute('SELECT count(*) FROM videos').fetchone()[0] == 1
    # The original record remains restorable even if availability was updated.
    monkeypatch.setattr(library_module, 'content_key', content_key)
    assert library.scan()['moved'] == 1
    target.rename(source)

    def changing_read(path, size, probe):
        key = content_key(path, size, probe)
        path.write_bytes(b'changed while sampling')
        return key

    monkeypatch.setattr(library_module, 'content_key', changing_read)
    assert library.scan()['deferred'] == 1
    with library.database.connect() as db:
        assert db.execute('SELECT path FROM videos WHERE id=?', (old['id'],)).fetchone()[0] == target.name


def test_move_transaction_rolls_back_all_dependents(library):
    source, old = seed(library)
    references(library, old)
    with library.database.connect() as db:
        db.execute("CREATE TRIGGER reject_move BEFORE UPDATE OF path ON videos BEGIN SELECT RAISE(ABORT,'Cannot move'); END")
    revision = library.database.revision()
    source.rename(source.with_name('Band - New (2000).mp4'))
    with pytest.raises(sqlite3.IntegrityError, match='Cannot move'):
        library.scan()
    assert library.get(old['id'])['path'] == source.name
    assert library.database.revision() == revision
    with library.database.connect() as db:
        assert db.execute('SELECT version FROM playlists').fetchone()[0] == 1
        db.execute('DROP TRIGGER reject_move')
    assert library.scan()['moved'] == 1


def test_loudness_callback_from_old_path_cannot_overwrite_retained_result(library):
    source, old = seed(library)
    references(library, old)
    source.rename(source.with_name('Band - New (2000).mp4'))
    assert library.scan()['moved'] == 1
    scanner = LoudnessScanner(library.settings, library.database)
    assert not scanner.save(old, {'status': 'error', 'error': 'Old path disappeared'})
    assert scanner.status()['measured'] == 1


def test_cancelled_backfill_is_resumable_without_catalog_changes(library, monkeypatch):
    for index in range(3):
        seed(library, f'Band - Song {index} (2000).mp4', data=f'media {index}'.encode())
    with library.database.connect() as db:
        db.execute('UPDATE videos SET content_key=NULL')
        db.execute('DELETE FROM loudness_jobs')
    revision = library.database.revision()
    stop = threading.Event()
    reads = []

    def cancelling_read(path, size, probe):
        reads.append(path)
        if len(reads) == 2:
            stop.set()
        return content_key(path, size, probe)

    with monkeypatch.context() as patch:
        patch.setattr(library_module, 'content_key', cancelling_read)
        result = library.scan(stop_event=stop)
        assert result['state'] == 'stopped' and result['fingerprinted'] == 1
    assert library.scan()['fingerprinted'] == 2
    assert library.database.revision() == revision
    with library.database.connect() as db:
        assert db.execute('SELECT count(*) FROM loudness_jobs').fetchone()[0] == 0


def test_old_repair_journal_still_recovers_after_upgrade(library, monkeypatch):
    source, old = seed(library, 'Band_Original (2000).mp4')
    references(library, old)
    repair = FilenameRepair(library.settings, library.database)
    target = source.with_name('Band - Original (2000).mp4')
    plan = {'repairs': [{'old_path': source.name, 'new_path': target.name}], 'hold': []}

    def interrupt(_):
        raise KeyboardInterrupt

    with monkeypatch.context() as patch:
        patch.setattr(repair, 'migrate', interrupt)
        with pytest.raises(KeyboardInterrupt):
            repair.apply(plan)
    legacy_id = hashlib.sha256(target.name.encode()).hexdigest()[:32]
    with library.database.connect() as db:
        db.execute('UPDATE filename_renames SET new_id=?', (legacy_id,))
    assert library.scan()['changed'] == 0
    assert repair.apply(plan)['recovered'] == 1
    assert library.source(legacy_id) == target
    with library.database.connect() as db:
        assert db.execute('SELECT video_id FROM playlist_items').fetchone()[0] == legacy_id
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_content_samples_are_bounded_and_duration_is_canonical(tmp_path, monkeypatch):
    source = tmp_path / 'large.mp4'
    with source.open('wb') as stream:
        stream.write(b'first')
        stream.seek(20 * SAMPLE_BYTES)
        stream.write(b'last')
    opened = Path.open
    reads = []

    class Reader:
        def __enter__(self):
            self.file = opened(source, 'rb')
            return self

        def __exit__(self, *_):
            self.file.close()

        def read(self, amount):
            data = self.file.read(amount)
            reads.append(len(data))
            return data

        def seek(self, offset):
            return self.file.seek(offset)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', lambda *_: Reader())
        key = content_key(source, source.stat().st_size, PROBE)
    assert reads == [SAMPLE_BYTES, SAMPLE_BYTES]
    assert key == content_key(source, source.stat().st_size, {'format': {'duration': '120'}})
    assert content_key(source, source.stat().st_size, {'format': {'duration': 'NaN'}}) is None
