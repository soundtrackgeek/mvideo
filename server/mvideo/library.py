import hashlib
import json
import logging
import os
import re
import stat as stat_module
import subprocess
import threading
from pathlib import Path
from time import perf_counter
from .parsing import parse_filename

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
                            "missing": 0, "pending": 0}
        stop = stop_event if stop_event is not None else threading.Event()
        try:
            root = self.settings.library.resolve(strict=True)
            if not root.is_dir():
                raise OSError("Library root unavailable")
            with self.database.connect() as db:
                existing = {row["id"]: (row["size"], row["mtime"], row["available"], row["probe_error"])
                            for row in db.execute("SELECT id,size,mtime,available,probe_error FROM videos")}
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
                            identity = hashlib.sha256(relative.encode()).hexdigest()[:32]
                            seen.add(identity)
                            self.scan_status["scanned"] += 1
                            if existing.get(identity) != (stat.st_size, stat.st_mtime_ns, 1, None):
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
                probe, error = None, None
                try:
                    probe = json.dumps(self.probe(path))
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    error = "Unable to inspect media; retry scan after checking FFprobe and file access"
                if stop.is_set() or not unchanged(candidate):
                    self.scan_status["deferred"] += 1
                    self.scan_status["pending"] -= 1
                    continue
                parsed = parse_filename(path.name)
                with self.database.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if stop.is_set() or not unchanged(candidate):
                        self.scan_status["deferred"] += 1
                        self.scan_status["pending"] -= 1
                        continue
                    override = db.execute("SELECT artist,title,year FROM overrides WHERE id=?", (identity,)).fetchone()
                    if override:
                        parsed.update(dict(override)); parsed["warnings"] = []
                    db.execute("""INSERT INTO videos VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
                        ON CONFLICT(id) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,artist=excluded.artist,
                        title=excluded.title,year=excluded.year,raw_name=excluded.raw_name,warnings=excluded.warnings,
                        probe=excluded.probe,probe_error=excluded.probe_error,available=1""",
                        (identity, relative, size, mtime, parsed["artist"], parsed["title"], parsed["year"], parsed["raw_name"], json.dumps(parsed["warnings"]), probe, error))
                    self._index(db, identity, parsed)
                    db.execute("""INSERT INTO loudness_jobs(video_id,size,mtime) VALUES(?,?,?)
                        ON CONFLICT(video_id) DO UPDATE SET size=excluded.size,mtime=excluded.mtime""",
                        (identity, size, mtime))
                    db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
                self.scan_status["changed"] += 1
                self.scan_status["pending"] -= 1
            if stop.is_set():
                self.scan_status["state"] = "stopped"
                return self.scan_status
            missing = [] if walk_errors else [identity for identity, row in existing.items() if row[2] and identity not in seen]
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
    def public(row):
        return {k: row[k] for k in ("id", "artist", "title", "year")} | {"warnings": json.loads(row["warnings"]), "probe_error": row["probe_error"]}

    def facets(self, kind, q="", limit=60, offset=0):
        expression = {"artists": "artist COLLATE NOCASE", "years": "year", "decades": "(year/10)*10"}[kind]
        where, params = self.scope(q=q)
        where += " AND " + ("artist IS NOT NULL" if kind == "artists" else "year IS NOT NULL")
        with self.database.connect() as db:
            total = db.execute(f"SELECT count(DISTINCT {expression}) FROM videos WHERE {where}", params).fetchone()[0]
            # Stable artwork from this exact scope, preferring a source with a successful probe.
            rows = db.execute(f"SELECT {expression} AS name, count(*) AS count, COALESCE(MIN(CASE WHEN probe_error IS NULL THEN id END), MIN(id)) AS representative_id FROM videos WHERE {where} GROUP BY {expression} ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?", [*params,limit,offset]).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "next_offset": offset+limit if offset+limit<total else None}
