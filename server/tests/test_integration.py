import json
import shutil
import subprocess
from fractions import Fraction
import pytest
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.library import Library
from mvideo.playback import Playback, playback_plan
from mvideo.metadata import Metadata


def test_partial_scan_and_cross_process_lock(tmp_path, monkeypatch):
    root = tmp_path/'media'; root.mkdir()
    settings = Settings(root, tmp_path/'state', file_stability_seconds=0); settings.prepare()
    db = Database(settings.state/'library.sqlite3')
    first = Library(settings, db); second = Library(settings, db)
    first.probe = lambda _: {'streams':[]}
    (root/'Artist - Song (2000).mp4').write_bytes(b'x')
    assert first.scan()['changed'] == 1
    def broken_walk(_):
        assert second.scan()['state'] == 'busy'
        raise PermissionError('inaccessible directory')
    monkeypatch.setattr('mvideo.library.os.scandir', broken_walk)
    assert first.scan()['state'] == 'warning'
    assert first.videos()['total'] == 1


def test_metadata_identity_and_verified_name_fallback(tmp_path, monkeypatch):
    settings = Settings(tmp_path/'media', tmp_path/'state'); settings.prepare()
    db = Database(settings.state/'library.sqlite3'); metadata = Metadata(db, settings)
    monkeypatch.setenv('LAST_FM','test-only'); monkeypatch.delenv('FANART_TV', raising=False)
    mbid = '7364dea6-ca9a-48e3-be01-b44ad0d19897'
    metadata.request = lambda *a, **k: {'artist':{'name':'a-ha','mbid':mbid,'bio':{'summary':'Candidate biography'}}}
    candidate = metadata.artist('a-ha')
    assert candidate['state'] == 'needs_identity' and candidate['biography'] is None
    with db.connect() as c:
        c.execute('INSERT INTO identities VALUES(?,?)',('a-ha',mbid))
        c.execute('DELETE FROM metadata')
    def response(url, params):
        if 'mbid' in params:
            return {'artist':{'name':'a‐ha','mbid':mbid,'url':'https://www.last.fm/music/a-ha','bio':{'summary':'Read more on Last.fm'}}}
        return {'artist':{'name':'a-ha','url':'https://www.last.fm/music/a-ha','bio':{'summary':'A Norwegian band. Read more on Last.fm'}}}
    metadata.request = response
    assert metadata.artist('a-ha')['biography'] == 'A Norwegian band.'


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg integration dependency unavailable')
def test_real_remux_and_anamorphic_conversion(tmp_path):
    root = tmp_path/'media'; root.mkdir()
    settings = Settings(root, tmp_path/'state', file_stability_seconds=0); settings.prepare()
    db = Database(settings.state/'library.sqlite3'); library = Library(settings, db)
    def make(name, codec, extra):
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=720x576:rate=25',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2','-vf','setsar=16/15',
            '-c:v',codec,*extra,'-c:a','aac','-ac','2',str(root/name)],check=True,capture_output=True)
    make('Artist - Anamorphic (2000).mkv','mpeg2video',[])
    make('Artist - Remux (2000).mkv','libx264',['-profile:v','high','-level:v','4.1'])
    assert library.scan()['changed'] == 2
    playback = Playback(settings, library)
    try:
        for identity in library.ids():
            row = library.get(identity); original = library.source(identity)
            before = (original.stat().st_size, original.stat().st_mtime_ns)
            source = json.loads(row['probe']); mode = playback_plan(source)
            expected = 'transcode' if row['title']=='Anamorphic' else 'remux'
            assert mode == expected
            target = settings.state/'playback'/(playback.cache_key(row)+'.mp4')
            playback.convert(identity,target,mode)
            output = library.probe(target)
            v = next(s for s in output['streams'] if s['codec_type']=='video')
            sar = Fraction((v['sample_aspect_ratio'] or '1:1').replace(':','/'))
            assert abs(float(v['width']/v['height']*sar)-4/3) < .005
            assert next(s for s in output['streams'] if s['codec_type']=='audio')['codec_name']=='aac'
            assert playback.thumbnail(identity).exists()
            for position in (0,.8,1.5):
                subprocess.run(['ffmpeg','-v','error','-ss',str(position),'-i',str(target),'-t','0.2','-f','null','-'],check=True,capture_output=True)
            assert before == (original.stat().st_size, original.stat().st_mtime_ns)
    finally: playback.close()
