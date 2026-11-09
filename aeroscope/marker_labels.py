"""Aircraft labels rendered next to a live icon; no extra ADS-B lookups."""
from __future__ import annotations

VALID_MODES = ('off', 'registration', 'icao')


def aircraft_marker_caption(plane, mode: str) -> str:
    """Return a compact, upper-case registration or ICAO24, as requested.

    Registration mode falls back to ICAO24 only when the API did not report
    the registration. Flight/callsign is intentionally not used as a fallback.
    """
    if mode not in VALID_MODES or mode == 'off':
        return ''
    registration = str(getattr(plane, 'registration', '') or '').strip().upper()
    icao = str(getattr(plane, 'hex', '') or '').strip().upper()
    raw = icao if mode == 'icao' else registration or icao
    # Do not render unexpected control characters or large arbitrary strings.
    safe = ''.join(c for c in raw if c.isalnum() or c == '-')
    return safe[:11] + '…' if len(safe) > 12 else safe
