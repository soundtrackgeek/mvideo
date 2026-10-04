import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unicodedata

import pytest

from mvideo.cli import main
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.filenames import FilenameRepair, load_plan, path_key
from mvideo.loudness import ANALYSIS_VERSION, LoudnessScanner, scan_lock
from mvideo.parsing import parse_filename


@pytest.fixture
def repair(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    settings = Settings(root, tmp_path / 'state', file_stability_seconds=0)
    settings.prepare()
    repair = FilenameRepair(settings, Database(settings.state / 'library.sqlite3'))
    repair.library.probe = lambda _: {'streams': [{'codec_type': 'audio', 'index': 1}]}
    return repair


def make_plan(old='Band_Song (2000).mp4', new='Band - Song (2000).mp4'):
    return {'version': 1, 'repairs': [{'old_path': old, 'new_path': new}], 'hold': []}


def seed(repair, names):
    for name in names:
        path = repair.settings.library / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('media bytes for ' + name).encode())
    repair.library.scan()
    with repair.database.connect() as db:
        return {row['path']: dict(row) for row in db.execute('SELECT * FROM videos')}


def test_preview_apply_references_overrides_measurements_and_idempotence(repair):
    plan = make_plan()
    old, new = plan['repairs'][0]['old_path'], plan['repairs'][0]['new_path']
    rows = seed(repair, [old, 'Other - Song (2001).mp4'])
    row = rows[old]
    old_id = row['id']
    new_id = hashlib.sha256(new.encode()).hexdigest()[:32]
    content = repair.path(old).read_bytes()
    with repair.database.connect() as db:
        db.execute("INSERT INTO playlists VALUES('mix','Mix','',1,0,0)")
        db.executemany("INSERT INTO playlist_items VALUES('mix',?,?)", [(old_id, 0), (rows['Other - Song (2001).mp4']['id'], 1)])
        db.execute('INSERT INTO overrides VALUES(?,?,?,?)', (old_id, 'User artist', 'User title', 2002))
        db.execute('''INSERT INTO audio_loudness VALUES(?,?,?,?,'measured',-20,-4,5,-30,1,'ffmpeg test',1,NULL)''',
                   (old_id, row['size'], row['mtime'], ANALYSIS_VERSION))
    revision = repair.database.revision()
    assert repair.preview(plan)['ready'] == 1
    assert repair.database.revision() == revision and repair.path(old).read_bytes() == content
    assert not repair.path(new).exists()
    result = repair.apply(plan)
    assert result['applied'] == 1 and result['manual'] == []
    assert repair.path(new).read_bytes() == content and repair.path(new).stat().st_mtime_ns == row['mtime']
    assert not repair.path(old).exists()
    with sqlite3.connect(result['backup']) as backup:
        assert backup.execute('SELECT path FROM videos WHERE id=?', (old_id,)).fetchone()[0] == old
    with repair.database.connect() as db:
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        video = dict(db.execute('SELECT * FROM videos WHERE id=?', (new_id,)).fetchone())
        assert (video['artist'], video['title'], video['year']) == ('User artist', 'User title', 2002)
        assert video['probe'] == row['probe'] and video['warnings'] == '[]'
        assert db.execute('SELECT version FROM playlists').fetchone()[0] == 2
        assert db.execute('SELECT video_id FROM playlist_items ORDER BY position').fetchone()[0] == new_id
        assert db.execute('SELECT id FROM overrides').fetchone()[0] == new_id
        assert db.execute('SELECT integrated_lufs FROM audio_loudness WHERE video_id=?', (new_id,)).fetchone()[0] == -20
        assert tuple(db.execute('SELECT size,mtime FROM loudness_jobs WHERE video_id=?', (new_id,)).fetchone()) == (row['size'], row['mtime'])
        assert db.execute('SELECT 1 FROM loudness_jobs WHERE video_id=?', (old_id,)).fetchone() is None
        assert db.execute('SELECT id FROM search WHERE search MATCH ?', ('"User artist"',)).fetchone()[0] == new_id
        assert db.execute('SELECT state FROM filename_renames').fetchone()[0] == 'complete'
    assert LoudnessScanner(repair.settings, repair.database).status()['measured'] == 1
    assert repair.library.scan()['changed'] == 0
    assert repair.apply(plan)['applied'] == 0
    assert repair.preview(plan)['already_done'] == 1


def test_complete_bundled_plan_and_user_years(repair):
    plan = load_plan()
    assert len(plan['repairs']) == 183 and len(plan['hold']) == 1
    names = [r['old_path'] for r in plan['repairs'] + plan['hold']]
    rows = seed(repair, names)
    assert repair.preview(plan)['ready'] == 184
    result = repair.apply(plan)
    assert result['applied'] == 184 and result['manual'] == []
    assert repair.library.scan()['changed'] == 0
    with repair.database.connect() as db:
        active = [dict(r) for r in db.execute('SELECT * FROM videos WHERE available=1')]
    assert len(active) == 183 and all(not parse_filename(r['path'])['warnings'] for r in active)
    for item in plan['repairs']:
        target = repair.path(item['new_path'])
        assert target.read_bytes() == ('media bytes for ' + item['old_path']).encode()
        # HFS/APFS may normalize Unicode; match the scanner's actual stored spelling.
        source = next(row for name, row in rows.items() if path_key(name) == path_key(item['old_path']))
        assert target.stat().st_mtime_ns == source['mtime']
    year_names = {r['path']: r['year'] for r in active}
    assert year_names['Farrenheit - Fool In Love (1987).mp4'] == 1987
    assert year_names['Miss Kittin & The Hacker - 1982 (1998).mpg'] == 1998
    assert (repair.hold_root / 'Matt Cox - Washed It All Away.mp4').is_file()
    assert repair.apply(plan)['already_done'] == 184


def test_hold_preserves_playlist_and_can_be_restored(repair):
    old = 'Matt Cox - Washed It All Away.mp4'
    plan = {'repairs': [], 'hold': [{'old_path': old}]}
    row = seed(repair, [old])[old]
    with repair.database.connect() as db:
        db.execute("INSERT INTO playlists VALUES('mix','Mix','',1,0,0)")
        db.execute("INSERT INTO playlist_items VALUES('mix',?,0)", (row['id'],))
    result = repair.apply(plan)
    assert Path(result['hold_directory']).parent == repair.settings.library.parent
    assert not repair.library.ids()
    with repair.database.connect() as db:
        assert db.execute('SELECT video_id FROM playlist_items').fetchone()[0] == row['id']
        assert db.execute('SELECT available FROM videos').fetchone()[0] == 0
    (repair.hold_root / old).rename(repair.path(old))
    repair.library.scan()
    assert repair.library.ids() == [row['id']]
    # A later owner-supplied year can repair the restored video while retaining the hold history.
    restored_plan = make_plan(old, 'Matt Cox - Washed It All Away (2000).mp4')
    assert repair.apply(restored_plan)['applied'] == 1
    with repair.database.connect() as db:
        assert db.execute('SELECT count(*) FROM filename_renames').fetchone()[0] == 2
        assert db.execute('SELECT video_id FROM playlist_items').fetchone()[0] == repair.library.ids()[0]


@pytest.mark.parametrize('action', ['rename', 'hold'])
def test_interruption_after_filesystem_move_resumes_database_migration(repair, monkeypatch, action):
    plan = make_plan() if action == 'rename' else {'repairs': [], 'hold': [{'old_path': 'Unknown.mp4'}]}
    old = (plan['repairs'] or plan['hold'])[0]['old_path']
    seed(repair, [old])
    migrate = repair.migrate
    def interrupt(_):
        raise KeyboardInterrupt
    monkeypatch.setattr(repair, 'migrate', interrupt)
    with pytest.raises(KeyboardInterrupt):
        repair.apply(plan)
    assert not repair.path(old).exists()
    with repair.database.connect() as db:
        assert db.execute('SELECT state FROM filename_renames').fetchone()[0] == 'pending'
        assert db.execute('SELECT path FROM videos').fetchone()[0] == old
    monkeypatch.setattr(repair, 'migrate', migrate)
    result = repair.apply(plan)
    assert result['recovered'] == 1 and result['applied'] == 0
    assert repair.preview(plan)['pending_recovery'] == 0


@pytest.mark.parametrize('failure', ['indexed_destination', 'unindexed_destination', 'changed_source', 'symlink'])
def test_conflicts_do_not_modify_any_media(repair, failure, tmp_path):
    plan = make_plan()
    old, new = plan['repairs'][0]['old_path'], plan['repairs'][0]['new_path']
    seed(repair, [old] + ([new] if failure == 'indexed_destination' else []))
    source, target = repair.path(old), repair.path(new)
    if failure == 'unindexed_destination':
        target.write_bytes(b'never overwrite this file')
    elif failure == 'changed_source':
        source.write_bytes(b'changed')
    elif failure == 'symlink':
        outside = tmp_path / 'outside.mp4'
        outside.write_bytes(b'outside')
        source.unlink()
        source.symlink_to(outside)
    before = {p.name: p.read_bytes() for p in repair.settings.library.iterdir()}
    assert repair.preview(plan)['conflict'] == 1
    with pytest.raises(ValueError, match='conflicts'):
        repair.apply(plan)
    assert before == {p.name: p.read_bytes() for p in repair.settings.library.iterdir()}
    with repair.database.connect() as db:
        assert db.execute('SELECT count(*) FROM filename_renames').fetchone()[0] == 0


def test_hold_destination_conflict_and_symlink(repair, tmp_path):
    old = 'Unknown.mp4'
    plan = {'repairs': [], 'hold': [{'old_path': old}]}
    seed(repair, [old])
    root = repair.hold_root
    root.mkdir()
    (root / old).write_bytes(b'keep')
    assert repair.preview(plan)['conflict'] == 1
    (root / old).unlink()
    root.rmdir()
    root.symlink_to(tmp_path / 'elsewhere')
    with pytest.raises(ValueError, match='symbolic link'):
        repair.apply(plan)
    assert repair.path(old).is_file()


def test_both_scan_locks_block_apply(repair):
    plan = make_plan()
    seed(repair, [plan['repairs'][0]['old_path']])
    for name in ['scan.lock', 'loudness.lock']:
        with scan_lock(repair.settings.state / name):
            with pytest.raises(RuntimeError, match='Another'):
                repair.apply(plan)
    assert repair.apply(plan)['applied'] == 1


def test_background_scan_between_interruption_and_resume(repair, monkeypatch):
    plan = make_plan()
    old, new = plan['repairs'][0]['old_path'], plan['repairs'][0]['new_path']
    seed(repair, [old])
    migrate = repair.migrate
    def interrupt(_):
        raise KeyboardInterrupt
    monkeypatch.setattr(repair, 'migrate', interrupt)
    with pytest.raises(KeyboardInterrupt):
        repair.apply(plan)
    repair.library.scan()
    with repair.database.connect() as db:
        assert db.execute('SELECT count(*) FROM videos').fetchone()[0] == 2
    monkeypatch.setattr(repair, 'migrate', migrate)
    assert repair.apply(plan)['recovered'] == 1
    with repair.database.connect() as db:
        assert db.execute('SELECT count(*) FROM videos').fetchone()[0] == 1
        assert db.execute('SELECT path FROM videos').fetchone()[0] == new


def test_filesystem_failure_does_not_update_catalog_and_is_retryable(repair, monkeypatch):
    plan = make_plan()
    old = plan['repairs'][0]['old_path']
    seed(repair, [old])
    finish = repair.finish
    def unavailable(_):
        raise PermissionError('Video is in use')
    monkeypatch.setattr(repair, 'finish', unavailable)
    with pytest.raises(PermissionError):
        repair.apply(plan)
    assert repair.path(old).is_file()
    assert repair.preview(plan)['pending_recovery'] == 1
    monkeypatch.setattr(repair, 'finish', finish)
    assert repair.apply(plan)['recovered'] == 1


def test_unicode_catalog_paths_and_missing_manual_entries(repair):
    actual = unicodedata.normalize('NFD', 'Björk_Song (2000).mp4')
    plan = make_plan(unicodedata.normalize('NFC', actual), 'Björk - Song (2000).mp4')
    seed(repair, [actual, 'Someone Unknown.mp4'])
    preview = repair.preview(plan)
    assert preview['ready'] == 1
    assert preview['manual'] == [{'old_path': 'Someone Unknown.mp4', 'warnings': ['missing_year', 'missing_artist']}]
    assert repair.apply(plan)['applied'] == 1
    assert repair.library.scan()['changed'] == 0


@pytest.mark.parametrize('old,new', [('../Bad.mp4', 'Band - Song (2000).mp4'),
    ('C:/Bad.mp4', 'Band - Song (2000).mp4'), ('Bad.mp4', 'Band - No year.mp4'),
    ('Bad.mp4', 'Band - Song (2000).mkv'), ('Bad.mp4', 'folder/Band - Song (2000).mp4'),
    ('Bad.mp4', 'Band - Song? (2000).mp4'), ('CON.mp4', 'Band - Song (2000).mp4')])
def test_invalid_plans_rejected(tmp_path, old, new):
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(make_plan(old, new)))
    with pytest.raises(ValueError):
        load_plan(path)


def test_cli_preview_is_default_and_apply_is_explicit(repair, monkeypatch, capsys, tmp_path):
    plan = make_plan()
    old = plan['repairs'][0]['old_path']
    seed(repair, [old])
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setenv('MVIDEO_LIBRARY', str(repair.settings.library))
    monkeypatch.setenv('MVIDEO_STATE', str(repair.settings.state))
    argv = ['mvideo', 'fix-filenames', '--plan', str(plan_path)]
    monkeypatch.setattr(sys, 'argv', argv)
    main()
    assert json.loads(capsys.readouterr().out)['ready'] == 1 and repair.path(old).exists()
    monkeypatch.setattr(sys, 'argv', argv + ['--apply'])
    main()
    assert '"applied": 1' in capsys.readouterr().out and not repair.path(old).exists()
