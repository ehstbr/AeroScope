"""Validated, monitor-independent XDG layout for the AeroScope dashboard.

A dashboard is a presentation, not a favorite. Weather subscriptions for active
widgets are kept separate from the user's saved favorite stations/airports.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

MAX_WIDGETS = 20
VERSION = 1


def layout_path():
    return (Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
            / 'aeroscope' / 'dashboard.json')


def widget_key(kind, code):
    kind = str(kind or '').lower()
    code = str(code or '').strip().upper()
    if kind not in ('airport', 'station', 'aircraft'):
        raise ValueError('Unsupported dashboard widget type')
    if not re.fullmatch({'airport': r'[A-Z0-9]{3}', 'station': r'[A-Z0-9]{4}',
                         'aircraft': r'[0-9A-F]{6}'}[kind], code):
        raise ValueError('Invalid dashboard widget code')
    return kind + ':' + code


def bounded_fraction(value, fallback):
    try:
        num = float(value)
        return max(0.0, min(1.0, num)) if math.isfinite(num) else fallback
    except (ValueError, TypeError):
        return fallback


def anchor_fraction(pixel, extent):
    """Normalized top-left offset relative to the *whole* overlay, not the card.

    A widget's width/height may change when folding/unfolding, but its anchor
    must not. Previously fractions were relative to the free space after
    subtracting the widget size, so a height change moved the top-left corner.
    """
    try:
        extent = float(extent)
        return bounded_fraction(float(pixel) / extent if extent > 0 else 0, 0)
    except (ValueError, TypeError, OverflowError):
        return 0


def anchor_pixel(fraction, extent, max_offset=None):
    """Restore an anchor on a new monitor; optionally keep it fully onscreen."""
    value = round(bounded_fraction(fraction, 0) * max(0, extent))
    return max(0, min(value, max_offset)) if max_offset is not None else value


def normalize(data):
    """Ignore broken/outdated/user-modified entries without losing valid cards."""
    result = {'version': VERSION, 'fullscreen': False, 'widgets': []}
    if not isinstance(data, dict):
        return result
    result['fullscreen'] = data.get('fullscreen') is True
    items = data.get('widgets', [])
    if not isinstance(items, list):
        return result
    seen = set()
    for entry in items:
        if not isinstance(entry, dict):
            continue
        kind, code = entry.get('kind'), entry.get('code')
        try:
            key = widget_key(kind, code)
        except ValueError:
            continue
        if key in seen:
            continue
        seen.add(key)
        result['widgets'].append({
            'kind': str(kind).lower(), 'code': str(code).strip().upper(),
            'x': bounded_fraction(entry.get('x'), 0.04),
            'y': bounded_fraction(entry.get('y'), 0.10),
            'collapsed': entry.get('collapsed') is True,
        })
        # Optional stable top-left anchor. Old 0.3.62 layouts have only x/y;
        # DashboardController migrates them using the original geometry.
        if 'anchor_x' in entry and 'anchor_y' in entry:
            result['widgets'][-1]['anchor_x'] = bounded_fraction(entry['anchor_x'], 0)
            result['widgets'][-1]['anchor_y'] = bounded_fraction(entry['anchor_y'], 0)
        # Persist station coordinates separately from METAR availability, so
        # a station-only widget can still check SIGMET after an app restart.
        if str(kind).lower() == 'station':
            try:
                lat, lon = float(entry['lat']), float(entry['lon'])
                if (math.isfinite(lat) and math.isfinite(lon) and
                        -90 <= lat <= 90 and -180 <= lon <= 180):
                    result['widgets'][-1]['lat'] = lat
                    result['widgets'][-1]['lon'] = lon
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
        if len(result['widgets']) >= MAX_WIDGETS:
            break
    return result


def load_layout(path=None):
    file = Path(path) if path else layout_path()
    try:
        return normalize(json.loads(file.read_text(encoding='utf-8')))
    except (ValueError, TypeError, OSError):
        return normalize({})


def save_layout(data, path=None):
    file = Path(path) if path else layout_path()
    normalized = normalize(data)
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_name(file.name + '.tmp')
    temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + '\n',
                         encoding='utf-8')
    os.replace(temporary, file)
