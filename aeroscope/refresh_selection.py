"""Pure selection policy for the header's manual-refresh split button.

"All" includes the aircraft radar and weather layers the user enabled.
Explicit METAR or SIGMET selection can refresh that product even if hidden,
without enabling a map layer or touching the ADS-B request timer.
"""
from __future__ import annotations


def refresh_targets(mode: str, *, metar_enabled: bool, sigmet_enabled: bool):
    """Return (refresh_aircraft, NOAA_product_tuple)."""
    if mode == 'all':
        return True, tuple(kind for kind, enabled in (
            ('metar', metar_enabled), ('sigmet', sigmet_enabled)) if enabled)
    if mode == 'aircraft':
        return True, ()
    if mode in ('metar', 'sigmet'):
        return False, (mode,)
    raise ValueError('Unknown manual refresh target')
