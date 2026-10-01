import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from mvideo.cli import main
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.loudness import ANALYSIS_VERSION, LoudnessScanner, parse_measurement, scan_lock


@pytest.fixture
def scanner(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    settings = Settings(root, tmp_path / 'state')
    settings.prepare()
    return LoudnessScanner(settings, Database(settings.state / 'library.sqlite3'))


def add_video(scanner, name='Song'):
    path = scanner.settings.library / f'Artist - {name} (2000).mkv'
    path.write_bytes(b'placeholder media')
    scanner.library.probe = lambda _: {'streams': [{'codec_type': 'audio', 'index': 1}]}
    scanner.library.scan()
    return scanner.library.videos(q=name)['items'][0]['id'], path


def result():
    return {'status': 'measured', 'integrated_lufs': -21.5, 'true_peak_dbtp': -5.0,
            'loudness_range_lu': 4.0, 'threshold_lufs': -31.5, 'audio_stream_index': 1}


def fake_analysis(scanner, monkeypatch):
    monkeypatch.setattr(scanner, 'preflight', lambda: None)
    calls = []
    def measure(path, row, timeout):
        calls.append(row['id'])
        return result()
    monkeypatch.setattr(scanner, 'measure', measure)
    return calls


def test_resume_force_changed_sources_and_analysis_version(scanner, monkeypatch):
    first, path = add_video(scanner, 'First')
    second, _ = add_video(scanner, 'Second')
    calls = fake_analysis(scanner, monkeypatch)
    assert scanner.run(limit=1)['measured'] == 1
    assert scanner.status()['pending'] == 1
    # A fresh object resumes from the committed database, not in-memory state.
    resumed = LoudnessScanner(scanner.settings, scanner.database)
    calls2 = fake_analysis(resumed, monkeypatch)
    assert resumed.run()['measured'] == 1
    assert len(set(calls + calls2)) == 2
    assert resumed.run()['cached'] == 2
    assert resumed.run(force=True, limit=1)['measured'] == 1
    path.write_bytes(b'replaced audio')
    scanner.library.scan()
    assert scanner.status()['stale'] == 1
    assert scanner.run()['measured'] == 1
    with scanner.database.connect() as db:
        db.execute('UPDATE audio_loudness SET analysis_version=? WHERE video_id=?', ('old', second))
    assert scanner.run()['measured'] == 1
    assert calls[-1] == second
    assert scanner.status()['measured'] == 2


def test_errors_continue_retry_and_silence_is_cached(scanner, monkeypatch):
    first, _ = add_video(scanner, 'First')
    second, _ = add_video(scanner, 'Second')
    fake_analysis(scanner, monkeypatch)
    def measure(path, row, timeout):
        if row['id'] == first:
            raise ValueError('Unreadable audio')
        return {'status': 'below_gate', 'integrated_lufs': None, 'true_peak_dbtp': None,
                'loudness_range_lu': 0, 'threshold_lufs': -70}
    monkeypatch.setattr(scanner, 'measure', measure)
    summary = scanner.run()
    assert summary['error'] == summary['below_gate'] == 1
    calls = fake_analysis(scanner, monkeypatch)
    assert scanner.run()['cached'] == 1
    assert calls == [first]
    with scanner.database.connect() as db:
        assert db.execute('SELECT integrated_lufs FROM audio_loudness WHERE video_id=?', (second,)).fetchone()[0] is None


def test_source_changes_before_during_and_concurrent_catalog_update(scanner, monkeypatch):
    identity, path = add_video(scanner)
    calls = fake_analysis(scanner, monkeypatch)
    path.write_bytes(b'changed without catalog scan')
    assert scanner.run()['error'] == 1
    assert calls == []
    scanner.library.scan()
    def change_during(path, row, timeout):
        path.write_bytes(path.read_bytes() + b'!')
        return result()
    monkeypatch.setattr(scanner, 'measure', change_during)
    assert scanner.run()['error'] == 1
    scanner.library.scan()
    def catalog_changes(path, row, timeout):
        with scanner.database.connect() as db:
            db.execute('UPDATE videos SET mtime=mtime+1 WHERE id=?', (identity,))
        return result()
    monkeypatch.setattr(scanner, 'measure', catalog_changes)
    assert scanner.run()['deferred'] == 1
    assert scanner.status()['stale'] == 1


def test_interruption_preserves_completed_work_and_releases_lock(scanner, monkeypatch):
    add_video(scanner, 'First')
    add_video(scanner, 'Second')
    fake_analysis(scanner, monkeypatch)
    def interrupt(event):
        if event['state'] == 'measured':
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        scanner.run(progress=interrupt)
    assert scanner.status()['measured'] == 1
    assert scanner.run()['measured'] == 1
    with scan_lock(scanner.settings.state / 'loudness.lock'):
        with pytest.raises(RuntimeError, match='Another loudness scan'):
            scanner.run()


def test_offline_root_does_not_replace_measurements(scanner, monkeypatch):
    add_video(scanner)
    fake_analysis(scanner, monkeypatch)
    scanner.run()
    monkeypatch.undo()
    scanner.settings.library.rename(scanner.settings.library.with_name('offline'))
    with pytest.raises(FileNotFoundError):
        scanner.run()
    assert scanner.status()['measured'] == 1


def test_unavailable_videos_and_path_escape(scanner, monkeypatch, tmp_path):
    identity, path = add_video(scanner)
    calls = fake_analysis(scanner, monkeypatch)
    outside = tmp_path / 'outside.mkv'
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    assert scanner.run()['error'] == 1
    assert calls == []
    scanner.library.scan()
    assert scanner.status()['total'] == 0
    assert scanner.run()['processed'] == 0


def test_parser_uses_input_stats_and_handles_below_gate():
    data = {'input_i': '-20.1', 'input_tp': '-1.2', 'input_lra': '8.0', 'input_thresh': '-30.1',
            'output_i': '-24.0', 'output_tp': '-5.1'}
    value = parse_measurement('Other log lines\n' + json.dumps(data) + '\nTrailer')
    assert value['integrated_lufs'] == -20.1 and value['true_peak_dbtp'] == -1.2
    data['input_i'] = '-inf'
    assert parse_measurement(json.dumps(data))['status'] == 'below_gate'
    data['input_tp'] = '-inf'
    assert parse_measurement(json.dumps(data))['true_peak_dbtp'] is None
    for key, bad in [('input_i', 'nan'), ('input_tp', 'inf'), ('input_lra', '-1'), ('input_thresh', None)]:
        invalid = data | {key: bad}
        with pytest.raises(ValueError):
            parse_measurement(json.dumps(invalid))
    with pytest.raises(ValueError):
        parse_measurement('Incomplete decode')


def test_decode_failure_and_timeout_cannot_save_partial_stats(scanner, monkeypatch):
    identity, path = add_video(scanner)
    fake_analysis(scanner, monkeypatch)
    monkeypatch.setattr(scanner, 'measure', LoudnessScanner.measure.__get__(scanner))
    row = scanner.library.get(identity)
    def failed(args, **kwargs):
        kwargs['stderr'].write(json.dumps({'input_i': '-20', 'input_tp': '-5',
                                          'input_lra': '0', 'input_thresh': '-30'}).encode())
        return subprocess.CompletedProcess(args, 1)
    monkeypatch.setattr(subprocess, 'run', failed)
    assert scanner.run()['error'] == 1
    assert scanner.status()['measured'] == 0
    def timed_out(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])
    monkeypatch.setattr(subprocess, 'run', timed_out)
    with pytest.raises(ValueError, match='timed out'):
        scanner.measure(path, row, 1)


def test_cli_status_validation_exit_codes_and_interruption(scanner, monkeypatch, capsys):
    add_video(scanner)
    monkeypatch.setenv('MVIDEO_LIBRARY', str(scanner.settings.library))
    monkeypatch.setenv('MVIDEO_STATE', str(scanner.settings.state))
    monkeypatch.setattr(sys, 'argv', ['mvideo', 'measure-loudness', '--status'])
    main()
    assert json.loads(capsys.readouterr().out)['pending'] == 1
    monkeypatch.setattr(sys, 'argv', ['mvideo', 'measure-loudness', '--limit', '0'])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    monkeypatch.setattr(sys, 'argv', ['mvideo', 'measure-loudness'])
    monkeypatch.setattr(LoudnessScanner, 'run', lambda *a, **kw: {'error': 1, 'deferred': 0})
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(LoudnessScanner, 'run', interrupted)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 130


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_real_audio_levels_first_track_silence_and_source_preservation(scanner):
    def make(name, audio=None, extra=None):
        args = ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=32x32:r=1:d=5']
        if audio:
            args += ['-f', 'lavfi', '-i', audio]
        if extra:
            args += ['-f', 'lavfi', '-i', extra]
        args += ['-map', '0:v']
        if audio:
            args += ['-map', '1:a']
        if extra:
            args += ['-map', '2:a']
        args += ['-t', '5', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', str(scanner.settings.library / f'Band - {name} (2000).mkv')]
        subprocess.run(args, check=True, capture_output=True)
    tone = 'sine=frequency=1000:sample_rate=48000:duration=5'
    make('Loud', tone)
    make('Quiet', tone + ',volume=0.1')
    make('Two tracks', tone + ',volume=0.1', tone)
    make('Silence', 'anullsrc=r=48000:cl=stereo')
    make('No audio')
    before = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
              for p in scanner.settings.library.iterdir()}
    scanner.library.scan()
    summary = scanner.run()
    assert summary['measured'] == 3 and summary['below_gate'] == summary['no_audio'] == 1
    assert summary['error'] == summary['deferred'] == 0
    with scanner.database.connect() as db:
        rows = {row['title']: dict(row) for row in db.execute(
            'SELECT v.title,a.* FROM audio_loudness a JOIN videos v ON v.id=a.video_id')}
    assert rows['Loud']['integrated_lufs'] - rows['Quiet']['integrated_lufs'] == pytest.approx(20, abs=.1)
    assert rows['Loud']['true_peak_dbtp'] - rows['Quiet']['true_peak_dbtp'] == pytest.approx(20, abs=.1)
    assert rows['Two tracks']['integrated_lufs'] == rows['Quiet']['integrated_lufs']
    assert rows['Two tracks']['audio_stream_index'] == 1
    assert rows['Silence']['integrated_lufs'] is None
    assert rows['No audio']['status'] == 'no_audio'
    assert all(row['analysis_version'] == ANALYSIS_VERSION and row['ffmpeg_version'].startswith('ffmpeg version') for row in rows.values())
    assert scanner.run()['cached'] == 5
    after = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
             for p in scanner.settings.library.iterdir()}
    assert before == after
    assert not list((scanner.settings.state / 'playback').iterdir())
