from collections import Counter, defaultdict
import json
import hashlib
import logging
import os
import re
import stat as stat_module
import subprocess
import threading
import time
import uuid
from pathlib import Path
from time import perf_counter
from .parsing import parse_filename
from .content import content_key, media_duration

EXTENSIONS = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".mpg", ".mpeg", ".vob", ".webm", ".wmv"}
logger = logging.getLogger(__name__)


class Library:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database
        self.scan_lock = threading.Lock()
        self.scan_status = {"state": "idle", "scanned": 0, "changed": 0, "deferred": 0}

    def probe(self, path):
        p = subprocess.run([self.settings.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                           capture_output=True, timeout=45)
        if p.returncode:
            raise ValueError("Media probe failed")
        result = json.loads(p.stdout)
        # Paths and FFmpeg tags are not part of the public catalog.
        return {"format": {k: result.get("format", {}).get(k) for k in ("format_name", "duration", "bit_rate")},
                "streams": [{k: s.get(k) for k in ("index", "codec_type", "codec_name", "profile", "level", "pix_fmt", "width", "height", "r_frame_rate", "field_order", "sample_aspect_ratio", "color_transfer", "channels", "sample_rate")} for s in result.get("streams", [])]}

    def scan(self, *, stop_event=None):
        if not self.scan_lock.acquire(blocking=False):
            return {'state': 'busy', 'error': 'Another scan is already running'}
        lock_file = None
        try:
            lock_file = (self.settings.state/'scan.lock').open('a+b')
            if lock_file.tell() == 0:
                lock_file.write(b'0'); lock_file.flush()
            lock_file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if lock_file: lock_file.close()
            self.scan_lock.release()
            return {'state':'busy', 'error':'Another scan is already running or its lock is unavailable'}
        self.scan_status = {"state": "scanning", "scanned": 0, "changed": 0, "deferred": 0,
                            "missing": 0, "pending": 0, "moved": 0, "fingerprinted": 0}
        stop = stop_event if stop_event is not None else threading.Event()
        try:
            root = self.settings.library.resolve(strict=True)
            if not root.is_dir():
                raise OSError("Library root unavailable")
            with self.database.connect() as db:
                existing = {row['path']: dict(row) for row in db.execute(
                    'SELECT id,path,size,mtime,available,probe,probe_error,content_key FROM videos')}
                journals = db.execute("SELECT old_id,new_id,old_path,new_path FROM filename_renames WHERE state='pending'").fetchall()
            protected_paths = {row[key] for row in journals for key in ('old_path', 'new_path')}
            protected_ids = {row[key] for row in journals for key in ('old_id', 'new_id')}
            seen = set()
            walk_errors = []
            def fail(error):
                walk_errors.append(type(error).__name__)
            # Collect stat data before changing availability. Partial/inaccessible walks never purge records.
            candidates = []
            directories = [root]
            while directories:
                if stop.is_set():
                    self.scan_status.update(state="stopped", deferred=len(candidates))
                    return self.scan_status
                directory = directories.pop()
                try:
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            if stop.is_set():
                                self.scan_status.update(state="stopped", deferred=len(candidates))
                                return self.scan_status
                            if entry.is_symlink():
                                continue
                            path = Path(entry.path)
                            if entry.is_dir(follow_symlinks=False):
                                if not (hasattr(path, "is_junction") and path.is_junction()):
                                    directories.append(path)
                                continue
                            if path.suffix.lower() not in EXTENSIONS:
                                continue
                            try:
                                stat = entry.stat(follow_symlinks=False)
                            except OSError as error:
                                walk_errors.append(type(error).__name__)
                                continue
                            relative = path.relative_to(root).as_posix()
                            seen.add(relative)
                            self.scan_status["scanned"] += 1
                            if relative in protected_paths:
                                continue  # Let the durable filename-repair journal finish first.
                            row = existing.get(relative)
                            identity = row['id'] if row else uuid.uuid4().hex
                            current = row and (row['size'], row['mtime'], row['available'], row['probe_error']) == (stat.st_size, stat.st_mtime_ns, 1, None)
                            backfill = current and row['content_key'] is None and media_duration(json.loads(row['probe'] or '{}')) is not None
                            if not current or backfill:
                                candidates.append((identity, relative, stat.st_size, stat.st_mtime_ns, path))
                except OSError as error:
                    fail(error)

            def unchanged(candidate):
                _, _, size, mtime, path = candidate
                try:
                    current = path.stat(follow_symlinks=False)
                    return stat_module.S_ISREG(current.st_mode) and (current.st_size, current.st_mtime_ns) == (size, mtime)
                except OSError:
                    return False

            # All candidates share one settling interval, including on large initial imports.
            self.scan_status.update(state="settling", pending=len(candidates))
            if candidates and stop.wait(self.settings.file_stability_seconds):
                self.scan_status.update(state="stopped", deferred=len(candidates), pending=0)
                return self.scan_status
            stable = []
            for candidate in candidates:
                if stop.is_set():
                    self.scan_status["deferred"] += self.scan_status["pending"]
                    self.scan_status.update(state="stopped", pending=0)
                    return self.scan_status
                if unchanged(candidate):
                    stable.append(candidate)
                else:
                    self.scan_status["deferred"] += 1
                    self.scan_status["pending"] -= 1
            self.scan_status["state"] = "probing"
            prepared = []
            for candidate in stable:
                if stop.is_set():
                    self.scan_status["deferred"] += self.scan_status["pending"]
                    self.scan_status.update(state="stopped", pending=0)
                    return self.scan_status
                identity, relative, size, mtime, path = candidate
                if not unchanged(candidate):
                    self.scan_status["deferred"] += 1
                    self.scan_status["pending"] -= 1
                    continue
                row = existing.get(relative)
                backfill = row and (row['size'], row['mtime'], row['available'], row['probe_error']) == (size, mtime, 1, None)
                probe, error, key = None, None, None
                try:
                    probe_data = json.loads(row['probe'] or '{}') if backfill else self.probe(path)
                    probe = json.dumps(probe_data)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    error = "Unable to inspect media; retry scan after checking FFprobe and file access"
                if error is None:
                    try:
                        key = content_key(path, size, probe_data)
                    except OSError:
                        self.scan_status['deferred'] += 1
                        self.scan_status['pending'] -= 1
                        continue
                if stop.is_set() or not unchanged(candidate):
                    self.scan_status["deferred"] += 1
                    self.scan_status["pending"] -= 1
                    continue
                if backfill:
                    with self.database.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        if stop.is_set() or not unchanged(candidate):
                            self.scan_status['deferred'] += 1
                            self.scan_status['pending'] -= 1
                            continue
                        db.execute('UPDATE videos SET content_key=? WHERE id=? AND size=? AND mtime=?',
                                   (key, identity, size, mtime))
                    row['content_key'] = key
                    self.scan_status['fingerprinted'] += 1
                    self.scan_status['pending'] -= 1
                else:
                    prepared.append((candidate, probe, error, key))

            # Resolve the whole batch before publishing any new paths. Multiple
            # missing copies or incoming copies are deliberately ambiguous.
            by_key = defaultdict(list)
            for relative, row in existing.items():
                if row['content_key']:
                    by_key[row['content_key']].append(row)
            incoming = Counter(key for _, _, _, key in prepared if key)

            def source_relocated(row, target):
                try:
                    source = root / row['path']
                    source_stat = source.lstat()
                    # Windows may still resolve the old spelling after a
                    # case-only rename. The walk saw only the new spelling.
                    if stat_module.S_ISREG(source_stat.st_mode) and source.samefile(target):
                        return True
                    seen.add(row['path'])
                    return False
                except FileNotFoundError:
                    return True
                except OSError:
                    walk_errors.append('MoveSourceUnavailable')
                    return None

            for candidate, probe, error, key in prepared:
                identity, relative, size, mtime, path = candidate
                if stop.is_set() or not unchanged(candidate):
                    self.scan_status['deferred'] += 1
                    self.scan_status['pending'] -= 1
                    continue
                matches = by_key.get(key, []) if relative not in existing and key else []
                old = matches[0] if len(matches) == incoming[key] == 1 else None
                if old and (old['path'] in seen or old['id'] in protected_ids):
                    old = None
                if old:
                    if source_relocated(old, path) is False:
                        old = None  # It reappeared after the walk; this is a copy.
                if old and walk_errors:
                    self.scan_status['deferred'] += 1
                    self.scan_status['pending'] -= 1
                    continue
                parsed = parse_filename(path.name)
                with self.database.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if stop.is_set() or not unchanged(candidate):
                        self.scan_status["deferred"] += 1
                        self.scan_status["pending"] -= 1
                        continue
                    if old:
                        absent = source_relocated(old, path)
                        if absent is None:
                            self.scan_status['deferred'] += 1
                            self.scan_status['pending'] -= 1
                            continue
                        if not absent:
                            old = None
                    if old:
                        identity = old['id']
                        self._relocate(db, old, relative, size, mtime, probe, key)
                        seen.add(old['path'])
                    else:
                        self._save_candidate(db, identity, relative, size, mtime, parsed, probe, error, key)
                    db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
                if old:
                    self.scan_status['moved'] += 1
                    logger.info('Video moved id=%s from=%r to=%r', identity, old['path'], relative)
                self.scan_status["changed"] += 1
                self.scan_status["pending"] -= 1
            if stop.is_set():
                self.scan_status["state"] = "stopped"
                return self.scan_status
            missing = [] if walk_errors else [row['id'] for relative, row in existing.items()
                if row['available'] and relative not in seen and row['id'] not in protected_ids]
            if missing:
                with self.database.connect() as db:
                    for identity in missing:
                        db.execute("UPDATE videos SET available=0 WHERE id=?", (identity,))
                        db.execute("DELETE FROM search WHERE id=?", (identity,))
                    db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
            self.scan_status["missing"] = len(missing)
            self.scan_status.update(state="warning" if walk_errors else "idle", inaccessible=len(walk_errors))
            if walk_errors:
                self.scan_status["error"] = "Some files could not be read; no missing records were removed"
        except (OSError, ValueError):
            self.scan_status.update(state="error", error="Library unavailable or scan incomplete; existing records retained")
        finally:
            lock_file.close()
            self.scan_lock.release()
        return self.scan_status

    def _save_candidate(self, db, identity, relative, size, mtime, parsed, probe, error, key):
        override = db.execute("SELECT artist,title,year FROM overrides WHERE id=?", (identity,)).fetchone()
        if override:
            parsed.update(dict(override)); parsed["warnings"] = []
        db.execute("""INSERT INTO videos(id,path,size,mtime,artist,title,year,raw_name,warnings,probe,probe_error,available,content_key)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?)
            ON CONFLICT(id) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,artist=excluded.artist,
            title=excluded.title,year=excluded.year,raw_name=excluded.raw_name,warnings=excluded.warnings,
            probe=excluded.probe,probe_error=excluded.probe_error,available=1,content_key=excluded.content_key""",
            (identity, relative, size, mtime, parsed["artist"], parsed["title"], parsed["year"], parsed["raw_name"], json.dumps(parsed["warnings"]), probe, error, key))
        self._index(db, identity, parsed)
        db.execute("""INSERT INTO loudness_jobs(video_id,size,mtime) VALUES(?,?,?)
            ON CONFLICT(video_id) DO UPDATE SET size=excluded.size,mtime=excluded.mtime""",
            (identity, size, mtime))

    @staticmethod
    def _relocate(db, old, relative, size, mtime, probe, key, error=None):
        """Shared atomic path/metadata update for scans and planned repairs."""
        identity = old['id']
        parsed = parse_filename(Path(relative).name)
        override = db.execute('SELECT artist,title,year FROM overrides WHERE id=?', (identity,)).fetchone()
        if override:
            parsed.update(dict(override)); parsed['warnings'] = []
        db.execute('''UPDATE videos SET path=?,size=?,mtime=?,artist=?,title=?,year=?,raw_name=?,warnings=?,
            probe=?,probe_error=?,available=1,content_key=? WHERE id=?''',
            (relative, size, mtime, parsed['artist'], parsed['title'], parsed['year'], parsed['raw_name'],
             json.dumps(parsed['warnings']), probe, error, key, identity))
        # A copy-and-delete move can change mtime. Only previously current
        # measurements may adopt the new stamp; stale ones must stay stale.
        db.execute('''UPDATE audio_loudness SET source_size=?,source_mtime=?
            WHERE video_id=? AND source_size=? AND source_mtime=?''',
            (size, mtime, identity, old['size'], old['mtime']))
        db.execute('UPDATE loudness_jobs SET size=?,mtime=? WHERE video_id=?', (size, mtime, identity))
        db.execute('''UPDATE playlists SET version=version+1,updated_at=? WHERE id IN
            (SELECT playlist_id FROM playlist_items WHERE video_id=?)''', (int(time.time()), identity))
        Library._index(db, identity, parsed)

    @staticmethod
    def _index(db, identity, data):
        db.execute("DELETE FROM search WHERE id=?", (identity,))
        db.execute("INSERT INTO search VALUES(?,?,?,?)", (identity, data["artist"] or "", data["title"], str(data["year"] or "")))

    def scope(self, q="", artist=None, year=None, decade=None, unknown=False, field="all", playlist=None):
        clauses, params = ["available=1"], []
        words = re.findall(r"[^\W_]+", q, flags=re.UNICODE)
        if q.strip():
            if not words:
                clauses.append("0")
            else:
                expression = " AND ".join('"' + x + '"*' for x in words)
                if field in ("artist", "title", "year"):
                    expression = f"{field}:({expression})"
                clauses.append("id IN (SELECT id FROM search WHERE search MATCH ?)")
                params.append(expression)
        for key, val in (("artist", artist), ("year", year)):
            if val is not None:
                clauses.append(f"{key}=?" + (" COLLATE NOCASE" if key == "artist" else "")); params.append(val)
        if decade is not None:
            clauses.append("year BETWEEN ? AND ?"); params += [decade, decade + 9]
        if unknown:
            clauses.append("year IS NULL")
        if playlist is not None:
            clauses.append("id IN (SELECT video_id FROM playlist_items WHERE playlist_id=?)")
            params.append(playlist)
        return " AND ".join(clauses), params

    @staticmethod
    def ordering(scope):
        if scope.get('playlist') is not None:
            return '(SELECT position FROM playlist_items WHERE playlist_id=? AND video_id=videos.id)', [scope['playlist']]
        return 'artist COLLATE NOCASE,title COLLATE NOCASE,id', []

    def videos(self, limit=48, offset=0, **scope):
        where, params = self.scope(**scope)
        order, order_params = self.ordering(scope)
        started = perf_counter()
        opened = counted = fetched = None
        try:
            with self.database.connect() as db:
                db.execute("BEGIN")
                revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
                opened = perf_counter()
                total = db.execute(f"SELECT count(*) FROM videos WHERE {where}", params).fetchone()[0]
                counted = perf_counter()
                rows = db.execute(f"SELECT * FROM videos WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", [*params, *order_params, limit, offset]).fetchall()
                fetched = perf_counter()
        finally:
            finished = perf_counter()
            if finished-started >= 2:
                # Missing checkpoints also identify a failing/stalled query.
                opened, counted, fetched = (finished if value is None else value for value in (opened, counted, fetched))
                logger.warning('Slow catalog videos total=%.3fs open_revision=%.3fs count=%.3fs page=%.3fs close=%.3fs',
                               finished-started, opened-started, counted-opened, fetched-counted, finished-fetched)
        return {"items": [self.public(r) for r in rows], "total": total, "offset": offset,
                "next_offset": offset+limit if offset+limit < total else None, "revision": revision}

    def ids(self, **scope):
        where, params = self.scope(**scope)
        order, order_params = self.ordering(scope)
        started = perf_counter()
        opened = fetched = None
        try:
            with self.database.connect() as db:
                opened = perf_counter()
                result = [r[0] for r in db.execute(f"SELECT id FROM videos WHERE {where} ORDER BY {order}", [*params, *order_params])]
                fetched = perf_counter()
            return result
        finally:
            finished = perf_counter()
            if finished-started >= 2:
                opened, fetched = (finished if value is None else value for value in (opened, fetched))
                logger.warning('Slow catalog ids total=%.3fs open=%.3fs query=%.3fs close=%.3fs',
                               finished-started, opened-started, fetched-opened, finished-fetched)

    def get(self, identity):
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM videos WHERE id=? AND available=1", (identity,)).fetchone()
        if not row:
            raise FileNotFoundError("Video no longer available")
        return row

    def source(self, identity):
        row = self.get(identity)
        root = self.settings.library.resolve(strict=True)
        path = (root / row["path"]).resolve(strict=True)
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError("Media is outside the configured library")
        return path

    @staticmethod
    def image_version(row):
        return hashlib.sha256(f"{row['id']}:{row['mtime']}:{row['size']}".encode()).hexdigest()

    @staticmethod
    def public(row):
        return {k: row[k] for k in ("id", "artist", "title", "year")} | {"warnings": json.loads(row["warnings"]), "probe_error": row["probe_error"], "thumbnail_version": Library.image_version(row)}

    def facets(self, kind, q="", limit=60, offset=0):
        expression = {"artists": "artist COLLATE NOCASE", "years": "year", "decades": "(year/10)*10"}[kind]
        where, params = self.scope(q=q)
        where += " AND " + ("artist IS NOT NULL" if kind == "artists" else "year IS NOT NULL")
        with self.database.connect() as db:
            db.execute('BEGIN')
            revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
            total = db.execute(f"SELECT count(DISTINCT {expression}) FROM videos WHERE {where}", params).fetchone()[0]
            # Stable artwork from this exact scope, preferring a source with a successful probe.
            rows = db.execute(f"SELECT {expression} AS name, count(*) AS count, COALESCE(MIN(CASE WHEN probe_error IS NULL THEN id END), MIN(id)) AS representative_id FROM videos WHERE {where} GROUP BY {expression} ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?", [*params,limit,offset]).fetchall()
            ids = [row['representative_id'] for row in rows]
            versions = {row['id']: self.image_version(row) for row in db.execute(
                f"SELECT id,mtime,size FROM videos WHERE id IN ({','.join('?' for _ in ids)})", ids)} if ids else {}
        return {"items": [dict(r) | {'thumbnail_version': versions[r['representative_id']]} for r in rows], "total": total, "next_offset": offset+limit if offset+limit<total else None, "revision": revision}
