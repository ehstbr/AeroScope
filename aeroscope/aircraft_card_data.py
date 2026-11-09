"""Compact, source-limited ADS-B facts for the floating aircraft card.

This module is deliberately GTK-free: all displayed information comes from
an already-received Aircraft object, never from flight history or a new API.
"""
from __future__ import annotations

import math

from .aircraft_art import aircraft_name
from .alerts import classify_alert
from .i18n import _, LANGUAGE


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _grouped(value):
    """Match the app's Portuguese thousands separator for whole aviation units."""
    text = f'{round(value):,}'
    return text.replace(',', '.') if LANGUAGE == 'pt_BR' else text


def speed_label(knots, unit='kmh'):
    """Use the same selectable units as the main inspector."""
    if not _finite(knots):
        return '—'
    multiplier, suffix = {
        'kmh': (1.852, 'km/h'),
        'kt': (1, 'kt'),
        'mph': (1.15077945, 'mph'),
    }.get(unit, (1.852, 'km/h'))
    return f'{_grouped(knots * multiplier)} {suffix}'


def vertical_rate_label(feet_per_minute):
    if not _finite(feet_per_minute):
        return '—'
    value = round(abs(feet_per_minute))
    if feet_per_minute > 0:
        return f'↑ {_grouped(value)} ft/min'
    if feet_per_minute < 0:
        return f'↓ {_grouped(value)} ft/min'
    return _('Level · 0 ft/min')


def heading_label(degrees):
    if not _finite(degrees):
        return '—'
    bearing = round(degrees) % 360
    cardinal = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')[
        int(((degrees % 360) + 22.5) // 45) % 8]
    return f'{bearing:03d}° {cardinal}'


def source_label(source):
    """Identify the reported position method without implying GPS precision."""
    name = str(source or '').strip().lower()
    return {
        'adsb_icao': 'ADS-B', 'adsb_icao_nt': 'ADS-B', 'adsb_other': 'ADS-B',
        'adsr_icao': 'ADS-R', 'adsr_other': 'ADS-R',
        'tisb_icao': 'TIS-B', 'tisb_other': 'TIS-B',
        'mlat': 'MLAT', 'mode_s': 'Mode S',
        'other': _('Other'),
    }.get(name, _('Unknown') if not name else name.upper()[:16])


def snapshot(plane, preferred_speed='kmh'):
    """Return the currently known facts, with explicit fallbacks for gaps.

    Do not infer destination, flight status or ground contact from missing data.
    The caller is responsible for showing whether the *position* is stale.
    """
    altitude = getattr(plane, 'altitude_ft', None)
    ground = getattr(plane, 'on_ground', None)
    if ground is True:
        altitude_text = _('On ground')
    elif _finite(altitude):
        altitude_text = f'{_grouped(altitude)} ft'
    else:
        altitude_text = '—'
    flight = str(getattr(plane, 'flight', '') or '').strip()
    registration = str(getattr(plane, 'registration', '') or '').strip()
    model = str(getattr(plane, 'model', '') or '').strip()
    squawk = str(getattr(plane, 'squawk', '') or '').strip()
    alert = classify_alert(squawk, getattr(plane, 'emergency', ''))
    lat, lon = getattr(plane, 'lat', None), getattr(plane, 'lon', None)
    location = f'{lat:.4f}, {lon:.4f}' if (_finite(lat) and _finite(lon)) else '—'
    return {
        'flight': flight or _('No callsign'),
        'registration': registration or _('No registration'),
        'model': aircraft_name(model),
        'icao_type': model.upper(),
        'icao24': str(getattr(plane, 'hex', '') or '').upper(),
        'altitude': altitude_text,
        'speed': speed_label(getattr(plane, 'speed_kts', None), preferred_speed),
        'vertical_rate': vertical_rate_label(getattr(plane, 'vertical_rate', None)),
        'heading': heading_label(getattr(plane, 'track', None)),
        'squawk': squawk or '—',
        'source': source_label(getattr(plane, 'source', '')),
        'position': location,
        'alert': alert.label if alert.level != 'none' else '',
        'alert_level': alert.level,
    }
