import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading

import pytest

from mvideo.cli import main
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.loudness import ANALYSIS_VERSION, LoudnessScanner, parse_measurement, scan_lock


@pytest.fixture
def scanner(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    settings = Settings(root, tmp_path / 'state', file_stability_seconds=0)
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


def test_targeted_scan_only_uses_requested_ids_and_preserves_cache_and_limit(scanner, monkeypatch):
    first, _ = add_video(scanner, 'First')
    second, _ = add_video(scanner, 'Second')
    third, _ = add_video(scanner, 'Third')
    calls = fake_analysis(scanner, monkeypatch)
    def all_ids():
        pytest.fail('Targeted scanning must not enumerate the whole catalog')
    monkeypatch.setattr(scanner.library, 'ids', all_ids)
    summary = scanner.run(ids=iter([second, second, third]), limit=1)
    assert summary['measured'] == summary['processed'] == 1
    assert calls == [second]
    assert scanner.status()['pending'] == 2
    summary = scanner.run(ids=[second, third], limit=1)
    assert summary['cached'] == summary['measured'] == 1
    assert calls == [second, third]
    assert scanner.run(ids=[second], force=True)['measured'] == 1
    assert calls == [second, third, second]
    assert scanner.run(ids=[])['processed'] == 0
    assert scanner.run(ids=['missing'])['deferred'] == 1
    assert scanner.current(scanner.library.get(first)) is False


def test_targeted_scan_lock_contention_does_not_process_or_mutate(scanner, monkeypatch):
    identity, _ = add_video(scanner)
    calls = fake_analysis(scanner, monkeypatch)
    with scan_lock(scanner.settings.state / 'loudness.lock'):
        with pytest.raises(RuntimeError, match='Another loudness scan'):
            scanner.run(ids=[identity], stop_event=threading.Event())
    assert calls == []
    assert scanner.status()['pending'] == 1
    assert scanner.run(ids=[identity])['measured'] == 1


@pytest.mark.parametrize('cancel', ['before', 'during', None])
def test_targeted_runs_never_query_full_catalog_status(scanner, monkeypatch, cancel):
    identity, _ = add_video(scanner)
    monkeypatch.setattr(scanner, 'preflight', lambda: None)
    def status():
        pytest.fail('Targeted runs must not aggregate the full catalog')
    monkeypatch.setattr(scanner, 'status', status)
    stopped = threading.Event()
    def measure(path, row, timeout, *, stop_event):
        if cancel == 'during':
            stop_event.set()
        return result()
    monkeypatch.setattr(scanner, 'measure', measure)
    if cancel == 'before':
        stopped.set()
    summary = scanner.run(ids=[identity], stop_event=stopped)
    assert 'catalog' not in summary
    assert summary['state'] == ('cancelled' if cancel else 'finished')


def test_preflight_reuses_capabilities_but_checks_library_availability(scanner, monkeypatch):
    first, _ = add_video(scanner, 'First')
    second, _ = add_video(scanner, 'Second')
    commands = []
    def run(args, **kwargs):
        commands.append(args)
        stdout = b' loudnorm ' if args[-1] == '-filters' else b'ffmpeg version test\n'
        return subprocess.CompletedProcess(args, 0, stdout=stdout)
    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(scanner, 'measure', lambda *args: result())
    assert scanner.run(ids=[first])['measured'] == 1
    assert scanner.run(ids=[second])['measured'] == 1
    summary = scanner.run()
    assert summary['cached'] == summary['catalog']['measured'] == 2
    assert [args[-1] for args in commands] == ['-filters', '-version']
    assert scanner.ffmpeg_version == 'ffmpeg version test'
    scanner.settings.library.rename(scanner.settings.library.with_name('offline'))
    with pytest.raises(FileNotFoundError):
        scanner.run(ids=[first])
    assert scanner.status()['measured'] == 2


@pytest.mark.parametrize('failure', ['filters', 'version'])
def test_failed_preflight_is_retried(scanner, monkeypatch, failure):
    attempts = {'filters': 0, 'version': 0}
    def run(args, **kwargs):
        stage = args[-1].removeprefix('-')
        attempts[stage] += 1
        if attempts[stage] == 1 and stage == failure:
            raise subprocess.CalledProcessError(1, args)
        stdout = b' loudnorm ' if stage == 'filters' else b'ffmpeg version test\n'
        return subprocess.CompletedProcess(args, 0, stdout=stdout)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        scanner.preflight()
    assert not scanner._preflight_complete
    scanner.preflight()
    scanner.preflight()
    assert attempts == {'filters': 2, 'version': 1 if failure == 'filters' else 2}


def test_cancellation_keeps_completed_work_and_interrupted_video_pending(scanner, monkeypatch):
    first, _ = add_video(scanner, 'First')
    second, _ = add_video(scanner, 'Second')
    fake_analysis(scanner, monkeypatch)
    stopped = threading.Event()
    def measure(path, row, timeout, *, stop_event):
        assert stop_event is stopped
        if row['id'] == second:
            stopped.set()
        return result()
    monkeypatch.setattr(scanner, 'measure', measure)
    summary = scanner.run(ids=[first, second], stop_event=stopped)
    assert summary['state'] == 'cancelled'
    assert summary['processed'] == summary['measured'] == 1
    assert summary['error'] == 0
    assert scanner.status()['pending'] == 1
    assert scanner.current(scanner.library.get(first))
    with scan_lock(scanner.settings.state / 'loudness.lock'):
        pass
    calls = fake_analysis(scanner, monkeypatch)
    assert scanner.run(ids=[second])['measured'] == 1
    assert calls == [second]


def test_already_cancelled_scan_skips_preflight_and_keeps_measurements(scanner, monkeypatch):
    identity, _ = add_video(scanner)
    fake_analysis(scanner, monkeypatch)
    scanner.run(ids=[identity])
    def preflight():
        pytest.fail('Cancelled scans must not launch FFmpeg')
    monkeypatch.setattr(scanner, 'preflight', preflight)
    stopped = threading.Event()
    stopped.set()
    summary = scanner.run(ids=[identity], force=True, stop_event=stopped)
    assert summary['state'] == 'cancelled' and summary['processed'] == 0
    assert scanner.status()['measured'] == 1


@pytest.mark.parametrize('cancel', [True, False])
def test_background_decode_stops_child_on_cancellation_or_timeout(scanner, monkeypatch, cancel):
    identity, _ = add_video(scanner)
    monkeypatch.setattr(scanner, 'preflight', lambda: None)
    stopped = threading.Event()
    popen = subprocess.Popen
    children = []
    commands = []
    def start(args, **kwargs):
        commands.append((args, kwargs))
        child = popen([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        children.append(child)
        if cancel:
            stopped.set()
        return child
    monkeypatch.setattr(subprocess, 'Popen', start)
    monkeypatch.setattr(shutil, 'which', lambda executable: '/usr/bin/nice')
    summary = scanner.run(ids=[identity], timeout=.05, stop_event=stopped)
    assert len(children) == 1 and children[0].poll() is not None
    assert 'preexec_fn' not in commands[0][1]
    if os.name != 'nt':
        assert commands[0][0][:3] == ['/usr/bin/nice', '-n', '10']
    if cancel:
        assert summary['state'] == 'cancelled' and summary['processed'] == 0
        assert scanner.status()['pending'] == 1 and scanner.status()['error'] == 0
    else:
        assert summary['state'] == 'finished' and summary['error'] == 1
        with scanner.database.connect() as db:
            saved = db.execute('SELECT error FROM audio_loudness WHERE video_id=?', (identity,)).fetchone()
        assert 'timed out' in saved['error']


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
    assert scanner.run(ids=[rows['Quiet']['video_id']], force=True,
                       stop_event=threading.Event())['measured'] == 1
    after = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
             for p in scanner.settings.library.iterdir()}
    assert before == after
    assert not list((scanner.settings.state / 'playback').iterdir())
