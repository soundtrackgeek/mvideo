"""Service-owned indexing and durable, single-file loudness work."""

import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserverVFS

from .library import EXTENSIONS
from .loudness import LoudnessScanner


logger = logging.getLogger(__name__)


def watch_entries(directory):
    # Match the scanner's boundary; polling must not recurse into linked trees.
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.is_symlink():
                continue
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                if not (hasattr(path, 'is_junction') and path.is_junction()):
                    yield entry
            elif path.suffix.lower() in EXTENSIONS:
                yield entry


class LibraryEvents(FileSystemEventHandler):
    def __init__(self, request_scan):
        self.request_scan = request_scan

    def on_any_event(self, event):
        if event.event_type not in {'created', 'modified', 'deleted', 'moved'}:
            return
        paths = (event.src_path, getattr(event, 'dest_path', ''))
        if event.is_directory or any(Path(path).suffix.lower() in EXTENSIONS for path in paths):
            # Bound the delay from the first event, even during a long copy burst.
            self.request_scan(delay=5)


class Ingestion:
    def __init__(self, settings, database, library, *, scan_interval=1800):
        self.settings, self.database, self.library = settings, database, library
        self.scan_interval = scan_interval
        self.scanner = LoudnessScanner(settings, database)
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.loudness_wake = threading.Event()
        self.scan_due = None
        self.observer = None
        self.threads = []
        self.watcher_status = {'mode': settings.watch_mode, 'state': 'off' if settings.watch_mode == 'off' else 'starting'}
        self.loudness_status = {'state': 'idle'}

    def start(self):
        if self.threads:
            return
        if self.scan_interval:
            self.request_scan()
        for name, target in (('mvideo-scan', self._scan_loop), ('mvideo-loudness', self._loudness_loop)):
            thread = threading.Thread(name=name, target=target, daemon=True)
            self.threads.append(thread)
            thread.start()

    def close(self):
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        self.loudness_wake.set()
        for thread in self.threads:
            thread.join()
        self.threads.clear()

    def request_scan(self, *, delay=0):
        with self.condition:
            due = time.monotonic() + delay
            self.scan_due = due if self.scan_due is None else min(due, self.scan_due)
            self.condition.notify_all()

    def status(self):
        with self.database.connect() as db:
            pending = db.execute('SELECT count(*) FROM loudness_jobs').fetchone()[0]
        return {'watcher': self.watcher_status.copy(), 'loudness': self.loudness_status.copy(),
                'pending_loudness': pending}

    def _stop_observer(self):
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def _watch(self):
        if self.settings.watch_mode == 'off':
            return
        if self.observer is not None:
            if self.observer.is_alive() and all(emitter.is_alive() for emitter in self.observer.emitters):
                return
            self._stop_observer()
        observer = (PollingObserverVFS(os.lstat, watch_entries, polling_interval=self.settings.watch_interval)
                    if self.settings.watch_mode == 'polling' else Observer(timeout=self.settings.watch_interval))
        try:
            observer.schedule(LibraryEvents(self.request_scan), str(self.settings.library), recursive=True)
            observer.start()
        except (OSError, RuntimeError):
            observer.stop()
            if observer.ident is not None:
                observer.join()
            self.watcher_status = {'mode': self.settings.watch_mode, 'state': 'retrying'}
            logger.warning('Library watcher unavailable; periodic scans remain enabled when configured')
        else:
            self.observer = observer
            self.watcher_status = {'mode': self.settings.watch_mode, 'state': 'watching'}
            # Reconcile anything that changed while no observer was attached.
            self.request_scan(delay=5)

    def _scan_loop(self):
        next_periodic = time.monotonic() + self.scan_interval
        next_watch = 0
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now >= next_watch:
                    self._watch()
                    next_watch = now + 30
                if self.scan_interval and now >= next_periodic:
                    self.request_scan()
                    next_periodic = now + self.scan_interval
                with self.condition:
                    if self.scan_due is None or self.scan_due > now:
                        delay = 1 if self.scan_due is None else min(1, max(0, self.scan_due - now))
                        self.condition.wait(timeout=delay)
                        continue
                    self.scan_due = None
                try:
                    result = self.library.scan(stop_event=self.stop_event)
                    if result.get('deferred') or result['state'] in {'busy', 'warning', 'error'}:
                        self.request_scan(delay=15)
                except Exception:
                    # Keep the scheduler alive after a transient disk/database failure.
                    logger.exception('Background library scan failed; retrying')
                    self.request_scan(delay=30)
                finally:
                    self.loudness_wake.set()
        finally:
            self._stop_observer()
            self.watcher_status = {'mode': self.settings.watch_mode, 'state': 'stopped'}

    def _next_job(self):
        with self.database.connect() as db:
            return db.execute('SELECT video_id,size,mtime FROM loudness_jobs ORDER BY rowid LIMIT 1').fetchone()

    def _finish_job(self, job):
        with self.database.connect() as db:
            # A later scan may have queued a newer source while FFmpeg was running.
            db.execute('DELETE FROM loudness_jobs WHERE video_id=? AND size=? AND mtime=?', tuple(job))

    def _measure_next(self):
        job = self._next_job()
        if job is None:
            self.loudness_status = {'state': 'idle'}
            return False
        try:
            self.library.get(job['video_id'])
        except FileNotFoundError:
            self._finish_job(job)
            return True
        self.loudness_status = {'state': 'measuring', 'id': job['video_id']}
        result = self.scanner.run(ids=[job['video_id']], stop_event=self.stop_event)
        if result['state'] == 'cancelled':
            return False
        if result.get('deferred'):
            self.request_scan(delay=15)
            self.loudness_status = {'state': 'waiting_for_scan'}
            return False
        self._finish_job(job)
        self.loudness_status = {'state': 'idle', 'last_result': 'error' if result.get('error') else 'complete'}
        return True

    def _loudness_loop(self):
        while not self.stop_event.is_set():
            self.loudness_wake.clear()
            retry = 5
            try:
                if self._measure_next():
                    continue
            except RuntimeError:
                # The manual bulk scanner/filename repair owns the same OS lock.
                self.loudness_status = {'state': 'waiting_for_lock'}
            except (OSError, ValueError, subprocess.SubprocessError, sqlite3.Error):
                self.loudness_status = {'state': 'retrying'}
                logger.warning('Automatic loudness analysis unavailable; queued work retained')
                retry = 30
            self.loudness_wake.wait(retry)
        self.loudness_status = {'state': 'stopped'}
