"""Resumable, read-only EBU R128 analysis of the catalog's first audio stream."""

from contextlib import contextmanager
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time

from .library import Library


# Bump when stream selection, channel mixing or measurement semantics change.
ANALYSIS_VERSION = 'first-audio-stereo-48k-r128-v1'
COMPLETE = {'measured', 'below_gate', 'no_audio'}
FIELDS = ('integrated_lufs', 'true_peak_dbtp', 'loudness_range_lu', 'threshold_lufs')


class AnalysisCancelled(Exception):
    """An interrupted measurement must remain pending rather than become an error."""


def parse_measurement(log):
    # Older FFmpeg versions emit JSON only on stderr, surrounded by log messages.
    blocks = re.findall(r'\{[^{}]*"input_i"\s*:[^{}]*\}', log)
    if not blocks:
        raise ValueError('FFmpeg did not return a complete loudness measurement')
    try:
        values = [float(json.loads(blocks[-1])[key]) for key in
                  ('input_i', 'input_tp', 'input_lra', 'input_thresh')]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('FFmpeg returned invalid loudness measurements') from error
    integrated, peak, spread, threshold = values
    # Silence / audio below the absolute gate has no usable integrated loudness.
    # Never save NaN/Infinity or invent a huge gain for it.
    if (any(math.isnan(value) or value == math.inf for value in values)
            or not math.isfinite(spread) or spread < 0 or not math.isfinite(threshold)
            or (math.isfinite(integrated) and not math.isfinite(peak))):
        raise ValueError('FFmpeg returned invalid loudness measurements')
    return dict(zip(FIELDS, (value if math.isfinite(value) else None for value in values))) | {
        'status': 'measured' if math.isfinite(integrated) else 'below_gate'}


@contextmanager
def scan_lock(path, label='loudness scan'):
    with path.open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError(f'Another {label} is running or its lock is unavailable') from error
        try:
            yield
        finally:
            # Closing also releases the lock after interruption or process exit.
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class LoudnessScanner:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database
        self.library = Library(settings, database)
        self.ffmpeg_version = ''
        self._preflight_complete = False

    def preflight(self):
        root = self.settings.library.resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Library root is unavailable')
        if self._preflight_complete:
            return
        result = subprocess.run([self.settings.ffmpeg, '-hide_banner', '-filters'],
                                capture_output=True, timeout=15, check=True)
        if not re.search(rb'\bloudnorm\s', result.stdout):
            raise ValueError('This FFmpeg build does not include the loudnorm filter')
        result = subprocess.run([self.settings.ffmpeg, '-version'],
                                capture_output=True, timeout=15, check=True)
        version = result.stdout.decode('utf-8', errors='replace').splitlines()
        if not version:
            raise ValueError('FFmpeg did not return its version')
        self.ffmpeg_version = version[0]
        self._preflight_complete = True

    @staticmethod
    def unchanged(path, row):
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns) == (row['size'], row['mtime'])

    def current(self, row):
        with self.database.connect() as db:
            saved = db.execute('SELECT * FROM audio_loudness WHERE video_id=?', (row['id'],)).fetchone()
        return (saved is not None and saved['status'] in COMPLETE
                and saved['analysis_version'] == ANALYSIS_VERSION
                and (saved['source_size'], saved['source_mtime']) == (row['size'], row['mtime']))

    def measure(self, path, row, timeout, stop_event=None):
        if stop_event is not None and stop_event.is_set():
            raise AnalysisCancelled
        probe = json.loads(row['probe'] or '{}')
        if row['probe_error'] or 'streams' not in probe:
            probe = self.library.probe(path)
        if stop_event is not None and stop_event.is_set():
            raise AnalysisCancelled
        audio = next((stream for stream in probe['streams'] if stream.get('codec_type') == 'audio'), None)
        if audio is None:
            return {'status': 'no_audio'}
        args = [self.settings.ffmpeg, '-nostdin', '-hide_banner', '-nostats', '-v', 'info',
                '-xerror', '-threads', '1', '-i', str(path), '-map', '0:a:0', '-vn', '-sn', '-dn',
                '-filter_threads', '1', '-af',
                'aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=print_format=json',
                '-threads', '1', '-f', 'null', '-']
        # Decode audio only, one file at a time. Discard the filter output: only
        # input_* statistics are saved, never normalized output or media files.
        priority = subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 0
        if stop_event is not None and os.name != 'nt' and (nice := shutil.which('nice')):
            args = [nice, '-n', '10', *args]
        with tempfile.TemporaryFile() as log:
            try:
                if stop_event is None:
                    result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=log,
                                            timeout=timeout, creationflags=priority)
                else:
                    if stop_event.is_set():
                        raise AnalysisCancelled
                    with subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=log,
                                          creationflags=priority) as result:
                        deadline = time.monotonic() + timeout
                        try:
                            while result.poll() is None:
                                remaining = deadline - time.monotonic()
                                if remaining <= 0:
                                    raise subprocess.TimeoutExpired(args, timeout)
                                if stop_event.wait(min(.1, remaining)):
                                    raise AnalysisCancelled
                        finally:
                            if result.poll() is None:
                                result.terminate()
                                try:
                                    result.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    result.kill()
                                    result.wait()
                    if stop_event.is_set():
                        raise AnalysisCancelled
            except subprocess.TimeoutExpired as error:
                raise ValueError('Audio analysis timed out; retry with a larger --timeout') from error
            if result.returncode:
                raise ValueError('FFmpeg could not decode the complete audio stream')
            # Bound memory even when a damaged input produces a large stderr log.
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 65536))
            measurement = parse_measurement(log.read().decode('utf-8', errors='replace'))
        return measurement | {'audio_stream_index': audio.get('index')}

    def save(self, row, measurement):
        with self.database.connect() as db:
            # A library scan can run while FFmpeg works. Do not attach an old
            # measurement to a replaced, removed or newly cataloged source.
            cursor = db.execute('''INSERT INTO audio_loudness
                (video_id,source_size,source_mtime,analysis_version,status,
                 integrated_lufs,true_peak_dbtp,loudness_range_lu,threshold_lufs,
                 audio_stream_index,ffmpeg_version,measured_at,error)
                SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?
                WHERE EXISTS(SELECT 1 FROM videos WHERE id=? AND size=? AND mtime=? AND available=1)
                ON CONFLICT(video_id) DO UPDATE SET
                 source_size=excluded.source_size,source_mtime=excluded.source_mtime,
                 analysis_version=excluded.analysis_version,status=excluded.status,
                 integrated_lufs=excluded.integrated_lufs,true_peak_dbtp=excluded.true_peak_dbtp,
                 loudness_range_lu=excluded.loudness_range_lu,threshold_lufs=excluded.threshold_lufs,
                 audio_stream_index=excluded.audio_stream_index,ffmpeg_version=excluded.ffmpeg_version,
                 measured_at=excluded.measured_at,error=excluded.error''',
                (row['id'], row['size'], row['mtime'], ANALYSIS_VERSION, measurement['status'],
                 *(measurement.get(key) for key in FIELDS), measurement.get('audio_stream_index'),
                 self.ffmpeg_version, int(time.time()), measurement.get('error'),
                 row['id'], row['size'], row['mtime']))
            return cursor.rowcount == 1

    def status(self):
        with self.database.connect() as db:
            rows = db.execute('''SELECT CASE
                WHEN a.video_id IS NULL THEN 'pending'
                WHEN a.source_size!=v.size OR a.source_mtime!=v.mtime OR a.analysis_version!=?
                    THEN 'stale'
                ELSE a.status END AS state, count(*) AS count
                FROM videos v LEFT JOIN audio_loudness a ON a.video_id=v.id
                WHERE v.available=1 GROUP BY state''', (ANALYSIS_VERSION,)).fetchall()
        counts = {name: 0 for name in ('pending', 'stale', 'measured', 'below_gate', 'no_audio', 'error')}
        counts.update({row['state']: row['count'] for row in rows})
        return {'total': sum(counts.values()), **counts, 'analysis_version': ANALYSIS_VERSION}

    def run(self, *, force=False, limit=None, timeout=1800, progress=None,
            ids=None, stop_event=None):
        """Measure all available videos, or only the supplied catalog IDs.

        Lock contention raises RuntimeError without processing any IDs. Callers
        with persistent jobs should retain them for a later attempt, including
        when the returned state is cancelled. Targeted runs omit the full
        catalog summary so processing a queue does not repeatedly scan it.
        """
        if (limit is not None and limit < 1) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Limit and timeout must be positive')
        progress = progress or (lambda event: None)
        counts = {key: 0 for key in ('processed', 'cached', 'measured', 'below_gate', 'no_audio', 'error', 'deferred')}
        include_catalog = ids is None
        def summary(state):
            result = {'state': state, **counts}
            if include_catalog:
                result['catalog'] = self.status()
            return result
        if stop_event is not None and stop_event.is_set():
            return summary('cancelled')
        with scan_lock(self.settings.state / 'loudness.lock'):
            self.preflight()
            ids = self.library.ids() if ids is None else list(dict.fromkeys(ids))
            progress({'state': 'starting', 'total': len(ids), 'limit': limit})
            for position, identity in enumerate(ids, 1):
                if stop_event is not None and stop_event.is_set():
                    break
                if limit is not None and counts['processed'] >= limit:
                    break
                try:
                    row = self.library.get(identity)
                except FileNotFoundError:
                    counts['deferred'] += 1
                    continue
                try:
                    source = self.library.source(identity)
                    if not self.unchanged(source, row):
                        raise ValueError('Source changed since indexing; run mvideo scan and retry')
                    if not force and self.current(row):
                        counts['cached'] += 1
                        continue
                    progress({'state': 'measuring', 'position': position, 'total': len(ids),
                              'id': identity, 'artist': row['artist'], 'title': row['title']})
                    measurement = (self.measure(source, row, timeout) if stop_event is None else
                                   self.measure(source, row, timeout, stop_event=stop_event))
                    if stop_event is not None and stop_event.is_set():
                        raise AnalysisCancelled
                    if not self.unchanged(source, row):
                        raise ValueError('Source changed during analysis; run mvideo scan and retry')
                except AnalysisCancelled:
                    return summary('cancelled')
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    measurement = {'status': 'error', 'error': str(error)[:500]}
                if stop_event is not None and stop_event.is_set():
                    return summary('cancelled')
                counts['processed'] += 1
                state = measurement['status'] if self.save(row, measurement) else 'deferred'
                counts[state] += 1
                progress({'state': state, 'position': position, 'total': len(ids), 'id': identity,
                          **{key: value for key, value in measurement.items() if key != 'status'}})
            state = 'cancelled' if stop_event is not None and stop_event.is_set() else 'finished'
            return summary(state)
