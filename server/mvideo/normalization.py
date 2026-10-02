"""Playback gain for the measured first-audio/stereo profile; never modifies media."""

import json
import math

from .loudness import ANALYSIS_VERSION


PROFILE = 'track-gain-v1'
TARGET_LUFS = -18.0
PEAK_CEILING_DBTP = -2.0
MAX_BOOST_DB = 12.0


def playback_normalization(library, identity):
    row = library.get(identity)
    with library.database.connect() as db:
        saved = db.execute('SELECT * FROM audio_loudness WHERE video_id=?', (identity,)).fetchone()
    def unavailable(reason):
        return {'state': 'unavailable', 'profile': PROFILE, 'reason': reason}
    if saved is None:
        return unavailable('not_measured')
    if saved['status'] != 'measured':
        return unavailable(saved['status'])
    if (saved['analysis_version'] != ANALYSIS_VERSION
            or (saved['source_size'], saved['source_mtime']) != (row['size'], row['mtime'])):
        return unavailable('stale_measurement')
    # Check the current source too: a file can change between periodic catalog scans.
    source = library.source(identity).stat()
    if (source.st_size, source.st_mtime_ns) != (row['size'], row['mtime']):
        return unavailable('source_changed')
    audio = next((s for s in json.loads(row['probe'] or '{}').get('streams', [])
                  if s.get('codec_type') == 'audio'), None)
    if row['probe_error'] or not audio or audio.get('index') != saved['audio_stream_index']:
        return unavailable('audio_track_changed')
    loudness, peak = saved['integrated_lufs'], saved['true_peak_dbtp']
    if (loudness is None or peak is None or not math.isfinite(loudness) or not math.isfinite(peak)
            or not -100 <= loudness <= 10 or not -100 <= peak <= 20):
        return unavailable('invalid_measurement')
    requested = TARGET_LUFS - loudness
    gain = min(requested, PEAK_CEILING_DBTP - peak, MAX_BOOST_DB)
    return {'state': 'ready', 'profile': PROFILE, 'gain_db': round(gain, 4),
            'target_lufs': TARGET_LUFS, 'integrated_lufs': loudness, 'true_peak_dbtp': peak,
            'peak_ceiling_dbtp': PEAK_CEILING_DBTP,
            'peak_limited': PEAK_CEILING_DBTP - peak < min(requested, MAX_BOOST_DB),
            'boost_limited': MAX_BOOST_DB < min(requested, PEAK_CEILING_DBTP - peak)}
