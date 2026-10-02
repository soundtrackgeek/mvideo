import copy
import json
import shutil
import subprocess
import time

import pytest

from mvideo.loudness import ANALYSIS_VERSION
from mvideo.loudness import parse_measurement
from mvideo.normalization import playback_normalization
from mvideo.playback import playback_plan
from test_service import PROBE, login, service


def measured(service, loudness=-24, peak=-10):
    app, client, root = service
    probe = copy.deepcopy(PROBE)
    probe['streams'][1]['index'] = 1
    app.state.library.probe = lambda _: probe
    (root / 'Band - Song (2000).mp4').write_bytes(b'original media')
    app.state.library.scan()
    row = app.state.library.get(app.state.library.ids()[0])
    with app.state.database.connect() as db:
        db.execute('''INSERT INTO audio_loudness VALUES(?,?,?,?,'measured',?,?,5,-34,1,'ffmpeg test',1,NULL)''',
                   (row['id'], row['size'], row['mtime'], ANALYSIS_VERSION, loudness, peak))
    return row


@pytest.mark.parametrize('loudness,peak,gain,peak_limited,boost_limited', [
    (-10.33, 1.42, -7.67, False, False), (-24.82, -7.3, 5.3, True, False),
    (-21.62, -9.08, 3.62, False, False), (-17.44, -1.25, -.75, True, False),
    (-50, -40, 12, False, True), (-18, -4, 0, False, False)])
def test_fixed_gain_peak_headroom_and_boost_limit(service, loudness, peak, gain, peak_limited, boost_limited):
    row = measured(service, loudness, peak)
    app, client, _ = service
    value = playback_normalization(app.state.library, row['id'])
    assert value['state'] == 'ready' and value['gain_db'] == pytest.approx(gain)
    assert value['peak_limited'] == peak_limited and value['boost_limited'] == boost_limited
    assert value['true_peak_dbtp'] + value['gain_db'] <= -2 + .0001
    result = client.post('/api/playback/' + row['id'], headers=login(app, client)).json()
    assert result['normalization'] == value and result['state'] == 'ready'
    assert result['mode'] == 'direct'
    assert client.get(result['url']).content == b'original media'


@pytest.mark.parametrize('update,reason', [
    ("status='error'", 'error'), ("status='below_gate'", 'below_gate'),
    ("status='no_audio'", 'no_audio'), ("source_size=0", 'stale_measurement'),
    ("source_mtime=0", 'stale_measurement'), ("analysis_version='old'", 'stale_measurement'),
    ("audio_stream_index=2", 'audio_track_changed'),
    ("integrated_lufs=NULL", 'invalid_measurement'), ("true_peak_dbtp=NULL", 'invalid_measurement'),
    ("integrated_lufs=-999", 'invalid_measurement')])
def test_unusable_results_do_not_block_playback_or_invent_gain(service, update, reason):
    row = measured(service)
    app, client, _ = service
    with app.state.database.connect() as db:
        db.execute('UPDATE audio_loudness SET ' + update)
    result = client.post('/api/playback/' + row['id'], headers=login(app, client)).json()
    assert result['state'] == 'ready'
    assert result['normalization']['reason'] == reason and 'gain_db' not in result['normalization']


def test_unindexed_changes_and_missing_measurements(service):
    row = measured(service)
    app, client, root = service
    (root / row['path']).write_bytes(b'changed source that has not been indexed')
    assert playback_normalization(app.state.library, row['id'])['reason'] == 'source_changed'
    with app.state.database.connect() as db:
        db.execute('DELETE FROM audio_loudness')
    assert playback_normalization(app.state.library, row['id'])['reason'] == 'not_measured'
    assert client.post('/api/playback/' + row['id']).status_code == 401


def test_multiple_audio_tracks_force_first_track_remux():
    probe = copy.deepcopy(PROBE)
    assert playback_plan(probe) == 'direct'
    probe['streams'].append(dict(probe['streams'][1], index=2))
    assert playback_plan(probe) == 'remux'


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_real_multiple_audio_rendition_retains_measured_first_track(service):
    app, client, root = service
    from mvideo.library import Library
    app.state.library.probe = Library.probe.__get__(app.state.library)
    source = root / 'Band - Two tracks (2000).mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=64x36:r=2:d=4',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=4',
                    '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=4',
                    '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'libx264', '-profile:v', 'high',
                    '-level:v', '4.1', '-c:a', 'aac', '-ac', '2', '-filter:a:0', 'volume=0.1',
                    '-disposition:a:0', '0', '-disposition:a:1', 'default', str(source)], check=True, capture_output=True)
    content = source.read_bytes()
    app.state.library.scan()
    identity = app.state.library.ids()[0]
    for _ in range(200):
        result = app.state.playback.prepare(identity)
        if result['state'] == 'ready': break
        assert result['state'] == 'preparing', result
        time.sleep(.02)
    assert result == {'state': 'ready', 'mode': 'remux'}
    target = app.state.playback.path(identity)
    assert len([s for s in app.state.library.probe(target)['streams'] if s['codec_type'] == 'audio']) == 1
    def measure(path):
        result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'info', '-i', str(path), '-map', '0:a:0',
            '-af', 'aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=print_format=json',
            '-f', 'null', '-'], capture_output=True, check=True, text=True)
        return parse_measurement(result.stderr)['integrated_lufs']
    assert measure(source) == pytest.approx(measure(target), abs=.05)
    assert source.read_bytes() == content
