from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path
import json
import random
import subprocess
import threading
import time


def make_queue(ids, shuffle=False, start=None):
    result = list(dict.fromkeys(ids))
    if shuffle:
        random.SystemRandom().shuffle(result)
    if start is not None:
        if start not in result:
            raise ValueError('Selected video is no longer in this selection')
        index = result.index(start)
        result = result[index:] + result[:index]
    return result


def playback_plan(probe):
    streams = probe.get('streams', [])
    video = next((s for s in streams if s.get('codec_type')=='video'), None)
    audio = next((s for s in streams if s.get('codec_type')=='audio'), None)
    if not video:
        return 'unsupported'
    if video.get('color_transfer') in ('smpte2084','arib-std-b67'):
        return 'unsupported_hdr'
    try:
        fps = float(Fraction(video.get('r_frame_rate') or '0'))
    except (ValueError, ZeroDivisionError):
        fps = 0
    video_ok = (video.get('codec_name')=='h264' and video.get('pix_fmt')=='yuv420p'
                and video.get('profile') in ('Baseline','Constrained Baseline','Main','High')
                and 0 < (video.get('level') or 0) <= 42
                and 0 < (video.get('width') or 0) <= 1920 and 0 < (video.get('height') or 0) <= 1080
                and 0 < fps <= 60 and video.get('field_order') in ('progressive', 'unknown', None))
    audio_ok = audio is None or (audio.get('codec_name')=='aac' and audio.get('profile')=='LC'
                                and (audio.get('channels') or 0)<=2 and int(audio.get('sample_rate') or 0)<=48000)
    container = probe.get('format',{}).get('format_name') or ''
    if video_ok and audio_ok and 'mp4' in container.split(','):
        return 'direct'
    if video_ok:
        return 'remux' if audio_ok else 'audio_transcode'
    return 'transcode'


class Playback:
    def __init__(self, settings, library):
        self.settings, self.library = settings, library
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mvideo-media')
        self.jobs = {}
        self.lock = threading.Lock()
        self.pins = {}
        self.thumbnail_lock = threading.Lock()

    def cache_key(self, row):
        return f"v2-{row['id']}-{row['mtime']}-{row['size']}"

    def prepare(self, identity):
        row = self.library.get(identity)
        if row['probe_error']:
            key = 'probe:' + identity
            with self.lock:
                job = self.jobs.get(key)
                if job and job.done():
                    del self.jobs[key]
                    if job.exception():
                        return {'state':'error','mode':'inspection','error':'Unable to inspect this file. Retry or skip it.'}
                if not job:
                    if sum(not j.done() for j in self.jobs.values()) >= 3:
                        return {'state':'busy','mode':'inspection'}
                    self.jobs[key] = self.pool.submit(self.inspect, identity)
            return {'state':'preparing','mode':'inspection'}
        probe = json.loads(row['probe'] or '{}')
        mode = playback_plan(probe)
        if mode.startswith('unsupported'):
            return {'state':'error', 'mode':mode, 'error':'Media needs manual compatibility review (missing probe or HDR)'}
        key = self.cache_key(row)
        with self.lock:
            self.pins[key] = time.time()+4*3600
            if mode=='direct':
                self.library.source(identity)
                return {'state':'ready','mode':mode}
            target = self.settings.state/'playback'/f'{key}.mp4'
            if target.exists():
                target.touch()
                return {'state':'ready','mode':mode}
            job = self.jobs.get(key)
            if job and job.done():
                if job.exception():
                    del self.jobs[key]
                    return {'state':'error','mode':mode,'error':'Conversion failed. Check FFmpeg, disk space and the source file; retry or skip.'}
            if not job:
                if len([j for j in self.jobs.values() if not j.done()])>=3:
                    return {'state':'busy','mode':mode}
                self.jobs = {k:j for k,j in self.jobs.items() if not j.done()}
                self.jobs[key] = self.pool.submit(self.convert, identity, target, mode)
            return {'state':'preparing','mode':mode}

    def convert(self, identity, target, mode):
        source = self.library.source(identity)
        # Bound storage before starting; active media tickets pin their outputs.
        self.prune()
        cache_used = sum(p.stat().st_size for p in (self.settings.state/'playback').glob('*.mp4'))
        row = self.library.get(identity)
        duration = float(json.loads(row['probe'] or '{}').get('format',{}).get('duration') or 0)
        estimate = row['size'] if mode=='remux' else max(row['size'] if mode=='audio_transcode' else 0, int(duration*1_100_000))
        if estimate <= 0 or estimate+cache_used > self.settings.cache_bytes:
            raise ValueError('Insufficient playback cache space')
        partial = target.with_suffix('.partial.mp4')
        args = [self.settings.ffmpeg,'-nostdin','-v','error','-y','-i',str(source),'-map','0:v:0','-map','0:a:0?','-sn','-dn','-map_metadata','-1']
        if mode=='transcode':
            args += ['-vf',"bwdif=mode=send_frame:parity=auto:deint=interlaced,scale=w='trunc(min(1920,min(iw*sar,1080*dar))/2)*2':h='trunc(ow/dar/2)*2',setsar=1,fps=30",
                     '-c:v','libx264','-preset','fast','-crf','20','-profile:v','high','-level:v','4.1','-pix_fmt','yuv420p','-maxrate','8M','-bufsize','16M']
        else:
            args += ['-c:v','copy']
        args += ['-c:a','copy'] if mode=='remux' else ['-c:a','aac','-b:a','192k','-ac','2','-ar','48000']
        args += ['-movflags','+faststart',str(partial)]
        try:
            result = subprocess.run(args,capture_output=True,timeout=3600)
            if result.returncode or not partial.exists():
                raise ValueError('Conversion failed')
            if partial.stat().st_size+cache_used > self.settings.cache_bytes:
                raise ValueError('Playback cache limit exceeded')
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)

    def path(self, identity):
        row = self.library.get(identity)
        if playback_plan(json.loads(row['probe'] or '{}'))=='direct':
            return self.library.source(identity)
        path = self.settings.state/'playback'/f'{self.cache_key(row)}.mp4'
        if not path.exists():
            raise FileNotFoundError('Prepared media expired; retry playback')
        return path

    def inspect(self, identity):
        probe = self.library.probe(self.library.source(identity))
        with self.library.database.connect() as db:
            db.execute('UPDATE videos SET probe=?,probe_error=NULL WHERE id=?', (json.dumps(probe), identity))

    def thumbnail(self, identity):
        row = self.library.get(identity)
        target = self.settings.state/'thumbnails'/f'{self.cache_key(row)}.jpg'
        with self.thumbnail_lock:
            if not target.exists():
                source = self.library.source(identity)
                temp = target.with_suffix('.partial.jpg')
                duration = float(json.loads(row['probe'] or '{}').get('format',{}).get('duration') or 10)
                position = str(min(10, max(0, duration * 0.1)))
                try:
                    r = subprocess.run([self.settings.ffmpeg,'-nostdin','-v','error','-y','-ss',position,'-i',str(source),'-frames:v','1','-vf',"scale=w=640:h='trunc(640/dar/2)*2',setsar=1",'-q:v','4',str(temp)],capture_output=True,timeout=30)
                    if r.returncode or not temp.exists():
                        raise FileNotFoundError('No thumbnail available')
                    temp.replace(target)
                finally:
                    temp.unlink(missing_ok=True)
        return target

    def prune(self):
        root = self.settings.state/'playback'
        files = sorted(root.glob('*.mp4'),key=lambda p:p.stat().st_mtime)
        size = sum(p.stat().st_size for p in files)
        for p in files:
            if size < self.settings.cache_bytes//2:
                break
            if self.pins.get(p.stem,0)<time.time():
                size -= p.stat().st_size
                p.unlink(missing_ok=True)

    def close(self):
        self.pool.shutdown(wait=True,cancel_futures=True)
