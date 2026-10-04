import hashlib
import shutil
import subprocess
import threading
import time

import pytest

from mvideo.config import Settings
from mvideo.database import Database
from mvideo.ingestion import Ingestion
from mvideo.library import Library
from mvideo.loudness import ANALYSIS_VERSION


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_ingestion_indexes_and_measures_real_video_without_changing_source(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    settings = Settings(root, tmp_path / 'state', watch_mode='off', file_stability_seconds=0)
    settings.prepare()
    database = Database(settings.state / 'library.sqlite3')
    library = Library(settings, database)
    source = root / 'Band - New Song (2000).mkv'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=32x32:r=1:d=2',
                    '-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=48000:duration=2',
                    '-map', '0:v', '-map', '1:a', '-t', '2', '-c:v', 'ffv1', '-c:a', 'pcm_s16le',
                    str(source)], check=True, capture_output=True)
    before = hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns
    worker = Ingestion(settings, database, library, scan_interval=0)
    worker.request_scan()
    worker.start()
    threads = list(worker.threads)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with database.connect() as db:
                measured = db.execute('''SELECT v.title,a.* FROM videos v
                    JOIN audio_loudness a ON a.video_id=v.id WHERE v.available=1''').fetchone()
                pending = db.execute('SELECT count(*) FROM loudness_jobs').fetchone()[0]
            if measured is not None and pending == 0:
                break
            threading.Event().wait(.01)
        assert measured is not None and pending == 0
        assert measured['title'] == 'New Song'
        assert measured['status'] == 'measured'
        assert measured['integrated_lufs'] < 0
        assert measured['audio_stream_index'] == 1
        assert measured['analysis_version'] == ANALYSIS_VERSION
        assert measured['ffmpeg_version'].startswith('ffmpeg version')
        assert library.videos()['total'] == 1
        assert (hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns) == before
        assert not list((settings.state / 'playback').iterdir())
    finally:
        worker.close()
    assert not any(thread.is_alive() for thread in threads)
