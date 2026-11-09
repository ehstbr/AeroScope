"""SIGMET coverage for airports/stations, independent of map overlay visibility.

Only report a horizontal polygon match and an advisory valid at the current time.
It is *not* an observation at the runway or a change to the METAR flight category.
Pure Python: no GTK or network operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

from .sigmet_readable import _point_in_polygon
from .weather_data import noaa_bbox


REGION_DEGREES = 4.0


def region_key(lat, lon):
    """Stable 4x4 degree cells; one NOAA request shared by nearby locations."""
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid SIGMET location')
    lat_i = min(44, int(math.floor((lat + 90) / REGION_DEGREES)))
    lon_i = min(89, int(math.floor((lon + 180) / REGION_DEGREES)))
    return lat_i, lon_i


def region_bbox(key):
    lat_i, lon_i = key
    center_lat = -90 + (lat_i + 0.5) * REGION_DEGREES
    center_lon = -180 + (lon_i + 0.5) * REGION_DEGREES
    return noaa_bbox(center_lat, center_lon)


def _timestamp(value):
    if value is None or value == '':
        return None
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            seconds = float(value)
            if seconds > 100_000_000_000:
                seconds /= 1000.0
            return seconds if math.isfinite(seconds) else None
        dt = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _meta(meta, *keys):
    for key in keys:
        value = meta.get(key)
        if value not in ('', None):
            return value
    return None


def currently_valid(advisory, now=None):
    """Check validity when NOAA supplies timestamps; absence is not invented."""
    meta = getattr(advisory, 'metadata', None) or {}
    start = _timestamp(_meta(meta, 'validTimeFrom', 'validFrom', 'startTime', 'validStart'))
    end = _timestamp(_meta(meta, 'validTimeTo', 'validTo', 'endTime', 'validEnd'))
    if now is None:
        now = datetime.now(timezone.utc).timestamp()
    return ((start is None or now >= start) and (end is None or now <= end))


def _contains(ring, lat, lon):
    """Point-in-polygon across the antimeridian, including the border."""
    if len(ring) < 3:
        return False
    # Unwrap consecutive longitudes, choose the nearest copy of the point.
    unwrapped = []
    previous = None
    for y, x in ring:
        x = float(x)
        if previous is not None:
            x += 360 * round((previous - x) / 360)
        unwrapped.append((float(y), x))
        previous = x
    xs = [x for _, x in unwrapped]
    shift = 360 * round(((min(xs) + max(xs)) / 2 - lon) / 360)
    px = lon + shift
    if not (min(xs) <= px <= max(xs)):
        return False
    ys = [y for y, _ in unwrapped]
    if not (min(ys) <= lat <= max(ys)):
        return False
    # Boundary points are considered covered, even when the ray caster would
    # otherwise classify an exactly-on-the-edge point as outside.
    for (y1, x1), (y2, x2) in zip(unwrapped, unwrapped[1:] + unwrapped[:1]):
        dx, dy = x2 - x1, y2 - y1
        cross = (px - x1) * dy - (lat - y1) * dx
        if abs(cross) < 1e-10 and min(x1, x2) - 1e-10 <= px <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= lat <= max(y1, y2) + 1e-10:
            return True
    return _point_in_polygon((lat, px), tuple(unwrapped))


def sigmets_covering(sigmets, lat, lon, *, now=None):
    """All active advisories whose horizontal contours contain the location."""
    try:
        lat, lon = float(lat), float(lon)
        region_key(lat, lon)
    except (ValueError, TypeError, OverflowError):
        return ()
    matches = []
    seen = set()
    for advisory in sigmets or ():
        if not currently_valid(advisory, now=now):
            continue
        if any(_contains(ring, lat, lon) for ring in advisory.rings):
            # Identical advisories from overlapping NOAA query geometries.
            marker = (advisory.name, advisory.text, advisory.rings)
            if marker not in seen:
                seen.add(marker)
                matches.append(advisory)
    return tuple(matches)
