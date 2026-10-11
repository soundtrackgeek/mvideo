"""Isolated real SSE/API fixture for native remote-focus verification.

Run: PYTHONPATH=server .venv/bin/python server/tests/tvos_sync_fixture.py
Only temporary, generated catalog records are changed by /_test/ routes.
"""
from pathlib import Path
import shutil
import tempfile
import time
import uvicorn
from mvideo.api import create_app
from mvideo.auth import digest
from mvideo.config import Settings


def main():
    with tempfile.TemporaryDirectory(prefix='mvideo-sync-ui-') as folder:
        root = Path(folder)/'media'
        root.mkdir()
        app = create_app(Settings(root, Path(folder)/'state', file_stability_seconds=0, watch_mode='off'), scan_interval=0)
        sample = Path(__file__).resolve().parents[2]/'apps/tvos/MVideoTests/Fixtures/Normalization.mp4'
        app.state.library.probe = lambda path: {'format': {'format_name': 'mp4'}, 'streams': [
            {'codec_type': 'video', 'codec_name': 'h264', 'pix_fmt': 'yuv420p', 'field_order': 'progressive'},
            {'codec_type': 'audio', 'codec_name': 'aac', 'channels': 2}]}

        @app.post('/_test/reset')
        def reset():
            for file in root.iterdir():
                file.unlink()
            for i in range(60):
                shutil.copyfile(sample, root/f'Library Band - Track {i:03} (2000).mp4')
            app.state.library.scan()
            with app.state.database.connect() as db:
                db.execute('INSERT OR REPLACE INTO pairing VALUES(1,?,?,0)', (digest('12345678'), int(time.time())+3600))
            return {'ok': True}

        @app.post('/_test/change')
        def change():
            for i in range(12):
                shutil.copyfile(sample, root/f'Library Band - Added {i:03} (2001).mp4')
            app.state.library.scan()
            return {'ok': True}

        reset()
        try:
            uvicorn.run(app, host='127.0.0.1', port=8766, lifespan='off', log_level='warning')
        finally:
            app.state.playback.close()
            app.state.metadata.close()


if __name__ == '__main__':
    main()
