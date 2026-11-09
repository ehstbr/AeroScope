"""Merge regional ADS-B alerts with the world's squawk-indexed lookup.

Only a matching ICAO24 may inherit a world-wide squawk status. Every global
association has a limited lifetime and never means a voice MAYDAY was issued.
"""
from __future__ import annotations
import time
from .alerts import classify_alert

_LEVELS = {'none': 0, 'info': 1, 'warning': 2, 'critical': 3}


def effective_alert(plane, global_rows, checked_at, interval=120, now=None):
    local = classify_alert(getattr(plane, 'squawk', ''), getattr(plane, 'emergency', ''))
    if now is None:
        now = time.time()
    try:
        age = float(now) - float(checked_at)
        ttl = max(90, min(360, 2 * int(interval) + 30))
    except (TypeError, ValueError, OverflowError):
        return local
    if age < 0 or age > ttl:
        return local
    icao = str(getattr(plane, 'hex', '') or '').lower()
    if not icao:
        return local
    best = local
    for row in global_rows or ():
        if not isinstance(row, dict) or str(row.get('hex') or '').lower() != icao:
            continue
        remote = classify_alert(row.get('squawk', ''))
        if _LEVELS[remote.level] > _LEVELS[best.level]:
            best = remote
    return best
