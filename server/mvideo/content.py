"""Bounded, versioned content keys for conservative relocation matching."""

from decimal import Decimal, InvalidOperation
import hashlib

SAMPLE_BYTES = 4 * 1024 * 1024


def media_duration(probe):
    try:
        duration = Decimal(str(probe.get('format', {}).get('duration')))
        if duration.is_finite() and duration > 0:
            return format(duration.normalize(), 'f')
    except (AttributeError, InvalidOperation, ValueError):
        pass
    return None


def content_key(path, size, probe):
    duration = media_duration(probe)
    if duration is None:
        return None
    digest = hashlib.sha256(f'content-v1:{size}:{duration}:'.encode())
    with path.open('rb') as source:
        first = source.read(min(size, SAMPLE_BYTES))
        if len(first) != min(size, SAMPLE_BYTES):
            raise OSError('Incomplete content sample')
        digest.update(first)
        tail_start = max(len(first), size - SAMPLE_BYTES)
        source.seek(tail_start)
        last = source.read(size - tail_start)
        if len(last) != size - tail_start:
            raise OSError('Incomplete content sample')
        digest.update(last)
    return 'v1:' + digest.hexdigest()
