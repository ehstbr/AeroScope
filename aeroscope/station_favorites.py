"""Durable ICAO weather station bookmarks, with coordinates for offline centering.

Only IDs/positions are saved, never METAR bulletins or device locations.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from .settings import CONFIG_DIR

FAVORITE_STATIONS_FILE = CONFIG_DIR / 'favorite_stations.json'


def normalized_station(code: str) -> str:
    code = str(code or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{4}', code):
        raise ValueError('Invalid ICAO weather station code')
    return code


def valid_position(lat, lon) -> tuple[float, float]:
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid weather station coordinates')
    return lat, lon


def load_station_favorites(path: Path = FAVORITE_STATIONS_FILE) -> dict[str, tuple[float, float]]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError, TypeError):
        return {}
    if not isinstance(data, list):
        return {}
    result = {}
    for item in data[:500]:
        if not isinstance(item, dict):
            continue
        try:
            code = normalized_station(item.get('icao'))
            result[code] = valid_position(item.get('lat'), item.get('lon'))
        except (ValueError, TypeError):
            continue
    return result


def save_station_favorites(stations: dict[str, tuple[float, float]],
                           path: Path = FAVORITE_STATIONS_FILE) -> None:
    entries = []
    for code, position in sorted(stations.items()):
        lat, lon = valid_position(*position)
        entries.append({'icao': normalized_station(code), 'lat': lat, 'lon': lon})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)
