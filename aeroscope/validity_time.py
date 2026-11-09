"""Pure time calculations for aviation advisory validity timelines.

A bar is displayed only when both provider timestamps form a valid interval.
Times are UTC. The bar indicates elapsed validity, never meteorological risk.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

START_KEYS = ('validTimeFrom', 'validFrom', 'startTime', 'validStart')
END_KEYS = ('validTimeTo', 'validTo', 'endTime', 'validEnd')


def parse_time(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    try:
        # NOAA can return ISO-8601, Unix seconds or milliseconds as numbers
        # or numeric strings; never interpret an ISO date as a number.
        if isinstance(value, (int, float)) or (isinstance(value, str) and
                                              value.strip().replace('.', '', 1).isdigit()):
            seconds = float(value)
            if seconds > 100_000_000_000:
                seconds /= 1000
            return seconds if math.isfinite(seconds) else None
        dt = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def validity_window(metadata):
    """Return (start,end) seconds, or None if a usable period is unavailable."""
    if not isinstance(metadata, dict):
        return None
    start = next((metadata[key] for key in START_KEYS
                  if metadata.get(key) not in (None, '')), None)
    end = next((metadata[key] for key in END_KEYS
                if metadata.get(key) not in (None, '')), None)
    start, end = parse_time(start), parse_time(end)
    if start is None or end is None or end <= start:
        return None
    return start, end


def elapsed_fraction(start, end, now=None):
    """0→1 elapsed share; never an intensity, severity or probability scale."""
    start, end = float(start), float(end)
    if not (math.isfinite(start) and math.isfinite(end)) or end <= start:
        return None
    if now is None:
        now = datetime.now(timezone.utc).timestamp()
    try:
        now = float(now)
        if not math.isfinite(now):
            return None
        return max(0.0, min(1.0, (now - start) / (end - start)))
    except (ValueError, TypeError, OverflowError):
        return None


def format_endpoint(seconds, *, full=False):
    dt = datetime.fromtimestamp(seconds, timezone.utc)
    return dt.strftime('%d/%m/%Y %H:%M UTC' if full else '%d/%m %H:%M')
