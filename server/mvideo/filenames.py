"""Apply an explicit filename repair plan and migrate dependent catalog records."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import sqlite3
import time
import unicodedata

from .library import Library, EXTENSIONS
from .loudness import scan_lock
from .parsing import parse_filename


def path_key(value):
    return unicodedata.normalize('NFC', value).casefold()


def validate_path(value):
    if not isinstance(value, str):
        raise ValueError('Media paths must be strings')
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or PureWindowsPath(value).drive
            or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in value.split('/'))
            or any(c in value for c in '\\:*?"<>|') or any(ord(c) < 32 for c in value)
            or path.suffix.lower() not in EXTENSIONS
            or any(PureWindowsPath(part).is_reserved() for part in path.parts)):
        raise ValueError('Invalid relative media path: ' + value)
    return path


def load_plan(path=None):
    path = path or Path(__file__).parent / 'data' / 'filename-repairs.json'
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(plan, dict) or plan.get('version') != 1:
        raise ValueError('Unsupported filename plan version')
    if not isinstance(plan.get('repairs'), list) or not isinstance(plan.get('hold', []), list):
        raise ValueError('Plan requires repairs and optional hold lists')
    old_keys, new_keys = set(), set()
    for item in plan['repairs']:
        if not isinstance(item, dict) or not {'old_path', 'new_path'} <= item.keys():
            raise ValueError('Each repair requires old_path and new_path')
        old, new = validate_path(item['old_path']), validate_path(item['new_path'])
        if old.parent != new.parent or old.suffix.lower() != new.suffix.lower():
            raise ValueError('Repairs must stay in the same directory and retain their media extension')
        if parse_filename(new.name)['warnings']:
            raise ValueError('New filename must be Artist - Title (Year): ' + str(new))
        old_key, new_key = path_key(str(old)), path_key(str(new))
        if old_key == new_key or old_key in old_keys or new_key in new_keys:
            raise ValueError('Duplicate or unchanged repair path')
        old_keys.add(old_key)
        new_keys.add(new_key)
    if old_keys & new_keys:
        raise ValueError('Chained or cyclic renames are not supported')
    for item in plan.get('hold', []):
        if not isinstance(item, dict) or 'old_path' not in item:
            raise ValueError('Each hold requires old_path')
        key = path_key(str(validate_path(item['old_path'])))
        if key in old_keys or key in new_keys:
            raise ValueError('Duplicate hold or repair path')
        old_keys.add(key)
    return plan


class FilenameRepair:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database
        self.library = Library(settings, database)

    def path(self, relative):
        validate_path(relative)
        root = self.settings.library.resolve(strict=True)
        path = root / relative
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError('Media path leaves the library or is a symbolic link')
        return path

    @property
    def hold_root(self):
        root = self.settings.library.resolve(strict=True)
        if not root.name:
            raise ValueError('The library must be a folder, not a drive root, to move a video aside')
        target = root.with_name(root.name + ' - Needs Review')
        if target.is_symlink() or target.resolve() != target:
            raise ValueError('Needs Review folder must not be a symbolic link or junction')
        return target

    def target(self, item):
        if item.get('action') != 'hold':
            return self.path(item['new_path'])
        relative = validate_path(item['new_path'])
        root = self.hold_root
        target = root / relative
        if target.is_symlink() or root not in target.resolve().parents:
            raise ValueError('Hold destination leaves the Needs Review folder')
        return target

    @staticmethod
    def unchanged(path, row):
        stat = path.stat()
        return path.is_file() and (stat.st_size, stat.st_mtime_ns) == (row['size'], row['mtime'])

    def preview(self, plan):
        with self.database.connect() as db:
            rows = {path_key(row['path']): dict(row) for row in db.execute('SELECT * FROM videos')}
            pending = db.execute("SELECT count(*) FROM filename_renames WHERE state='pending'").fetchone()[0]
            held = {row['old_id']: dict(row) for row in db.execute(
                "SELECT * FROM filename_renames WHERE action='hold' AND state='complete'")}
        repairs = []
        actions = [dict(item, action='rename') for item in plan['repairs']]
        actions += [dict(item, action='hold', new_path=item['old_path']) for item in plan.get('hold', [])]
        for item in actions:
            row, target_row = rows.get(path_key(item['old_path'])), rows.get(path_key(item['new_path']))
            result = dict(item)
            if row is None or not row['available']:
                done = bool(target_row and target_row['available']) if item['action'] == 'rename' else bool(row and row['id'] in held)
                result['state'] = 'already_done' if done else 'not_in_catalog'
            else:
                result['old_path'] = row['path']  # Preserve the Windows catalog's exact Unicode spelling.
                try:
                    if not self.unchanged(self.path(row['path']), row):
                        raise ValueError('Source changed since indexing; scan the library first')
                    if (item['action'] == 'rename' and target_row is not None) or self.target(item).exists():
                        raise ValueError('Destination already exists; no file will be overwritten')
                    result['state'] = 'ready'
                except (OSError, ValueError) as error:
                    result.update(state='conflict', error=str(error))
            repairs.append(result)
        planned = {path_key(item['old_path']) for item in actions}
        manual = []
        for row in rows.values():
            if row['available'] and path_key(row['path']) not in planned:
                parsed = parse_filename(Path(row['path']).name)
                if parsed['warnings']:
                    manual.append({'old_path': row['path'], 'warnings': parsed['warnings']})
        return {'repairs': repairs, 'manual': manual, 'pending_recovery': pending,
                'hold_directory': str(self.hold_root) if plan.get('hold') else None,
                **{state: sum(item['state'] == state for item in repairs)
                   for state in ('ready', 'already_done', 'not_in_catalog', 'conflict')}}

    def backup(self):
        directory = self.settings.state / 'backups'
        directory.mkdir(exist_ok=True)
        path = directory / f'before-filename-repairs-{time.time_ns()}.sqlite3'
        with self.database.connect() as source:
            target = sqlite3.connect(path)
            try:
                source.backup(target)
            finally:
                target.close()
        return path

    def migrate(self, journal):
        parsed = parse_filename(Path(journal['new_path']).name)
        old_id, new_id = journal['old_id'], journal['new_id']
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA defer_foreign_keys=ON')
            old = db.execute('SELECT * FROM videos WHERE id=?', (old_id,)).fetchone()
            if old is None or (old['path'], old['size'], old['mtime']) != (
                    journal['old_path'], journal['source_size'], journal['source_mtime']):
                raise ValueError('Catalog changed during repair; keep the journal and database backup')
            if journal['action'] == 'rename':
                destination = db.execute('SELECT * FROM videos WHERE id=? OR path=?', (new_id, journal['new_path'])).fetchone()
                if destination:
                    # An automatic scan may have seen a completed filesystem rename after
                    # an interruption. Discard only its unreferenced, matching duplicate row.
                    matches = (destination['id'], destination['path'], destination['size'], destination['mtime']) == (
                        new_id, journal['new_path'], journal['source_size'], journal['source_mtime'])
                    referenced = any(db.execute(f'SELECT 1 FROM {table} WHERE {column}=?', (new_id,)).fetchone()
                                     for table, column in [('playlist_items', 'video_id'),
                                                           ('audio_loudness', 'video_id'), ('overrides', 'id')])
                    if not matches or referenced:
                        raise ValueError('Destination was cataloged separately with changed data or references; repair requires reconciliation')
                    db.execute('DELETE FROM search WHERE id=?', (new_id,))
                    db.execute('DELETE FROM videos WHERE id=?', (new_id,))
            # Version bumps ensure an open playlist editor cannot save stale IDs over this change.
            db.execute('''UPDATE playlists SET version=version+1,updated_at=? WHERE id IN
                (SELECT playlist_id FROM playlist_items WHERE video_id=?)''', (int(time.time()), old_id))
            if journal['action'] == 'hold':
                # Keep its original ID and all references so returning the file and scanning restores it.
                db.execute('UPDATE videos SET available=0 WHERE id=?', (old_id,))
                db.execute('DELETE FROM search WHERE id=?', (old_id,))
                db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
                db.execute("UPDATE filename_renames SET state='complete' WHERE id=?", (journal['id'],))
                return
            db.execute('''UPDATE videos SET id=?,path=?,artist=?,title=?,year=?,raw_name=?,warnings=?,available=1
                WHERE id=?''', (new_id, journal['new_path'], parsed['artist'], parsed['title'], parsed['year'],
                               parsed['raw_name'], json.dumps(parsed['warnings']), old_id))
            db.execute('UPDATE playlist_items SET video_id=? WHERE video_id=?', (new_id, old_id))
            db.execute('UPDATE audio_loudness SET video_id=? WHERE video_id=?', (new_id, old_id))
            db.execute('UPDATE overrides SET id=? WHERE id=?', (new_id, old_id))
            override = db.execute('SELECT artist,title,year FROM overrides WHERE id=?', (new_id,)).fetchone()
            if override:
                # Existing explicit user metadata keeps its priority over filename parsing.
                parsed.update(dict(override))
                db.execute('UPDATE videos SET artist=?,title=?,year=?,warnings=? WHERE id=?',
                           (parsed['artist'], parsed['title'], parsed['year'], '[]', new_id))
            db.execute('DELETE FROM search WHERE id=?', (old_id,))
            Library._index(db, new_id, parsed)
            db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
            db.execute("UPDATE filename_renames SET state='complete' WHERE id=?", (journal['id'],))

    def finish(self, journal):
        source, target = self.path(journal['old_path']), self.target(journal)
        stamp = {'size': journal['source_size'], 'mtime': journal['source_mtime']}
        if journal['action'] == 'hold':
            target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            if not self.unchanged(source, stamp):
                raise ValueError('Source changed since the repair was prepared')
            if target.exists():
                # Unix no-overwrite rename below may be interrupted between link and unlink.
                if os.name == 'nt' or not source.samefile(target):
                    raise ValueError('Both filenames exist; refusing to overwrite either file')
                source.unlink()
            elif os.name == 'nt':
                # On Windows os.rename fails if the target exists, including a racing writer.
                source.rename(target)
            else:
                # Same-volume hard link + unlink never overwrites an existing destination.
                os.link(source, target)
                source.unlink()
        elif not target.exists():
            raise FileNotFoundError('Both source and destination are missing; repair not applied')
        if not self.unchanged(target, stamp):
            raise ValueError('Renamed file does not match the saved source size and modification time')
        # The pending journal was committed before touching the filesystem. A rerun can
        # finish this migration if interrupted between the rename and SQLite commit.
        self.migrate(journal)

    def apply(self, plan, progress=None):
        progress = progress or (lambda item: None)
        with scan_lock(self.settings.state / 'scan.lock', 'library scan'), scan_lock(self.settings.state / 'loudness.lock'):
            backup = self.backup()
            progress({'state': 'backed_up', 'backup': str(backup)})
            with self.database.connect() as db:
                pending = [dict(row) for row in db.execute("SELECT * FROM filename_renames WHERE state='pending'")]
            recovered = 0
            for journal in pending:
                self.finish(journal)
                recovered += 1
            preview = self.preview(plan)
            if preview['conflict']:
                raise ValueError('Filename conflicts detected; run the preview to inspect them. No new repairs applied.')
            applied = 0
            for item in preview['repairs']:
                if item['state'] != 'ready':
                    continue
                with self.database.connect() as db:
                    row = dict(db.execute('SELECT * FROM videos WHERE path=?', (item['old_path'],)).fetchone())
                    new_id = hashlib.sha256(item['new_path'].encode()).hexdigest()[:32] if item['action'] == 'rename' else row['id']
                    cursor = db.execute('''INSERT INTO filename_renames
                        (old_id,new_id,old_path,new_path,source_size,source_mtime,original_row,state,action,created_at)
                        VALUES(?,?,?,?,?,?,?,'pending',?,?)''',
                               (row['id'], new_id, row['path'], item['new_path'], row['size'], row['mtime'],
                                json.dumps(row, ensure_ascii=False), item['action'], int(time.time())))
                    journal = dict(db.execute('SELECT * FROM filename_renames WHERE id=?', (cursor.lastrowid,)).fetchone())
                self.finish(journal)
                applied += 1
                progress({'state': 'moved_aside' if item['action'] == 'hold' else 'renamed',
                          'old_path': item['old_path'], 'destination': str(self.target(item))})
            return {'state': 'complete', 'applied': applied, 'recovered': recovered, 'backup': str(backup),
                    'manual': preview['manual'], 'already_done': preview['already_done'],
                    'not_in_catalog': preview['not_in_catalog'], 'hold_directory': preview['hold_directory']}
