"""Persist only the viewport last chosen in AeroScope (not GPS location)."""
from __future__ import annotations
import json
import math
from pathlib import Path
from .settings import CONFIG_DIR

VIEW_FILE = CONFIG_DIR / 'last-map-view.json'


def validated_view(data):
    if not isinstance(data, dict):
        return None
    try:
        lat, lon, zoom = (float(data[k]) for k in ('lat', 'lon', 'zoom'))
    except (TypeError, ValueError, KeyError, OverflowError):
        return None
    if not (all(map(math.isfinite, (lat, lon, zoom))) and
            -85 <= lat <= 85 and -180 <= lon <= 180 and 1 <= zoom <= 19):
        return None
    return (lat, lon, zoom)


def load_view(path=VIEW_FILE):
    try:
        return validated_view(json.loads(Path(path).read_text('utf-8')))
    except (OSError, ValueError, TypeError):
        return None


def save_view(lat, lon, zoom, path=VIEW_FILE):
    values = validated_view({'lat': lat, 'lon': lon, 'zoom': zoom})
    if values is None:
        return False
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix('.json.tmp')
    temp.write_text(json.dumps(dict(zip(('lat', 'lon', 'zoom'), values))) + '\n', encoding='utf-8')
    temp.replace(file)
    return True
