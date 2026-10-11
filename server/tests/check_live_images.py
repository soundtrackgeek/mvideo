"""Opt-in Windows deployment check; never collected by pytest.

Run with installed service Python (-I): check_live_images.py backup, then
update the service and run check_live_images.py verify. Uses a SQLite backup,
checks both existing routes, and always removes its five-minute test session.
No source videos, playlists, measurements or provider mappings are changed.
"""
import hashlib
import io
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import time

import httpx

from mvideo.auth import digest


STATE = Path(r'C:\ProgramData\mvideo')
BACKUP = STATE/'backups'/'before-image-cache-0.15.0-20261011.sqlite3'
EVIDENCE = Path('output/image015')
ROUTES = ('http://127.0.0.1:8765', 'https://jorncomputer.tail5ef358.ts.net:8443')


def snapshot(db):
    result = {}
    for table in ('videos', 'audio_loudness', 'playlists', 'playlist_items', 'overrides', 'identities', 'sessions', 'loudness_jobs'):
        # The already-running identity backfill may continue across the upgrade.
        columns = [row[1] for row in db.execute(f'PRAGMA table_info({table})') if row[1] != 'content_key']
        rows = sorted([list(row) for row in db.execute(f'SELECT {",".join(columns)} FROM {table}')], key=lambda row: json.dumps(row))
        result[table] = {'count': len(rows), 'sha256': hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
    result['revision'] = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
    return result


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('backup', 'verify'):
        raise SystemExit('Usage: check_live_images.py backup|verify')
    database = STATE/'library.sqlite3'
    assert database.is_file(), 'Installed database missing'
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == 'backup':
        assert not BACKUP.exists(), 'Backup already exists; retain it and review before repeating'
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as source, sqlite3.connect(BACKUP) as target:
            source.backup(target)
            assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            baseline = snapshot(target)
        (EVIDENCE/'baseline.json').write_text(json.dumps(baseline, indent=2))
        print(json.dumps({'backup': str(BACKUP), 'integrity': 'ok', 'counts': {key: value['count'] for key, value in baseline.items() if isinstance(value, dict)}}))
        return

    baseline = json.loads((EVIDENCE/'baseline.json').read_text())
    from PIL import Image
    with sqlite3.connect(database) as db:
        db.execute('BEGIN')
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert snapshot(db) == baseline, 'Existing catalog/measurements/playlists/session state changed'
        ids = {row[0] for row in db.execute('SELECT id FROM videos WHERE available=1')}
        artist = next((name for name, text, mbid in db.execute('''SELECT m.artist,m.data,i.mbid FROM metadata m
                       LEFT JOIN identities i ON i.artist=m.artist COLLATE NOCASE
                       WHERE EXISTS (SELECT 1 FROM videos v WHERE v.artist=m.artist COLLATE NOCASE AND available=1)''')
                       if (data := json.loads(text)).get('background_count', 0) > 0
                       and ((mbid and data.get('mbid') == mbid) or
                            (not mbid and data.get('identity_source') == 'musicbrainz_recording' and data.get('mbid')))), None)
    assert artist, 'No cached artist background is available'
    token = secrets.token_urlsafe(32)
    session = digest(token)
    results = {}
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO sessions VALUES(?,?)', (session, int(time.time())+300))
    try:
        for origin in ROUTES:
            with httpx.Client(base_url=origin, timeout=90, headers={'Authorization': 'Bearer '+token}) as client:
                assert client.get('/health').json()['version'] == '0.15.0'
                page = client.get('/api/videos').raise_for_status().json()
                again = client.get('/api/videos').raise_for_status().json()
                assert page['items'][0]['thumbnail'] == again['items'][0]['thumbnail']
                queue = client.post('/api/queue', json={'shuffle': True}).raise_for_status().json()['ids']
                assert len(queue) == len(ids) and set(queue) == ids
                photo = client.get('/api/artist', params={'name': artist, 'background': True}).raise_for_status().json()['images'][0]
                sizes = {}
                original = client.get(photo).raise_for_status()
                with Image.open(io.BytesIO(original.content)) as image:
                    native_width = image.width
                for width in (640, 1280, 1920):
                    sized = client.get(photo+'&width='+str(width)).raise_for_status()
                    assert sized.headers['cache-control'] == 'private, max-age=3600'
                    with Image.open(io.BytesIO(sized.content)) as image:
                        assert image.width == min(width, native_width)
                        sizes[str(width)] = {'pixels': list(image.size), 'bytes': len(sized.content)}
                    cached = client.get(photo+'&width='+str(width)).raise_for_status()
                    assert cached.content == sized.content and cached.headers['etag'] == sized.headers['etag']
                assert client.get(photo+'&width=800').status_code == 422
                results[origin] = {'home': len(page['items']), 'available': len(ids), 'stable_urls': True,
                                   'original_bytes': len(original.content), 'renditions': sizes}
    finally:
        with sqlite3.connect(database) as db:
            db.execute('DELETE FROM sessions WHERE hash=?', (session,))
    for origin in ROUTES:
        with httpx.Client(base_url=origin, timeout=30, headers={'Authorization': 'Bearer '+token}) as client:
            assert client.get('/api/videos').status_code == 401
            assert client.get(photo+'&width=640').status_code == 401
    with sqlite3.connect(database) as db:
        db.execute('BEGIN')
        assert snapshot(db) == baseline
        results['content_keys'] = db.execute('SELECT count(*) FROM videos WHERE available=1 AND content_key IS NOT NULL').fetchone()[0]
    results['state_retained'] = True
    results['test_session_revoked'] = True
    (EVIDENCE/'verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
