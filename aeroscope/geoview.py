"""Pure Web-Mercator view coverage and trajectory fitting.

GNOME/libshumate draws the map; this module deliberately has no GTK imports so
it can be tested on a build server. ADSB.lol caps an area query at 250 NM.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MAX_LAT = 85.05112878
EARTH_NM = 3440.065
TILE_SIZE = 256


def clamp_lat(lat):
    return max(-MAX_LAT, min(MAX_LAT, float(lat)))


def lon_wrap(lon):
    return (lon + 180) % 360 - 180


def lon_to_x(lon):
    return (float(lon) + 180) / 360


def lat_to_y(lat):
    r = math.radians(clamp_lat(lat))
    return (1 - math.asinh(math.tan(r)) / math.pi) / 2


def x_to_lon(x):
    return lon_wrap(360 * float(x) - 180)


def y_to_lat(y):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * float(y)))))


def distance_nm(lat1, lon1, lat2, lon2):
    a1, a2 = math.radians(lat1), math.radians(lat2)
    da = a2 - a1
    dl = math.radians(lon_wrap(lon2 - lon1))
    h = math.sin(da / 2)**2 + math.cos(a1) * math.cos(a2) * math.sin(dl / 2)**2
    return EARTH_NM * 2 * math.asin(min(1, math.sqrt(max(0, h))))


@dataclass(frozen=True)
class RadarCoverage:
    queries: tuple[tuple[float, float, int], ...]
    complete: bool
    bounds: tuple[float, float, float, float]  # south, west (unwrapped), north, east
    center: tuple[float, float]
    farthest_nm: float


def coverage_for_view(lat, lon, zoom, width, height, *, max_queries=6, max_radius=245, buffer_area=1.0):
    """Cover the viewport with up to max_queries circles, each <=250 NM.

    If a zoomed-out map would require excessive API requests, return limited
    center coverage with `complete=False` instead of claiming worldwide data.
    Latitude/longitude correspond to map center at requested zoom.
    """
    lat, lon = clamp_lat(lat), lon_wrap(lon)
    width, height = max(1, int(width)), max(1, int(height))
    world = TILE_SIZE * 2.0 ** max(0, zoom)
    cx, cy = lon_to_x(lon), lat_to_y(lat)
    # 4x geographic screen area means 2x viewport width AND 2x height.
    # Input value is area multiplier, not per-dimension multiplier.
    scale = math.sqrt(max(1.0, float(buffer_area)))
    half_w, half_h = scale * width / (2 * world), scale * height / (2 * world)
    left, right = cx - half_w, cx + half_w
    top, bottom = max(0, cy - half_h), min(1, cy + half_h)
    south, north = y_to_lat(bottom), y_to_lat(top)
    farthest = max(distance_nm(lat, lon, y_to_lat(y), x_to_lon(x))
                   for x in (left, right) for y in (top, bottom))
    if farthest <= max_radius:
        radius = max(5, min(max_radius, math.ceil(farthest + 6)))
        return RadarCoverage(((lat, lon, radius),), True,
                             (south, 360*left-180, north, 360*right-180), (lat, lon), farthest)

    best = None
    # Split by map tiles in Mercator coordinates; not equally by latitude.
    for cols in range(1, max_queries + 1):
        for rows in range(1, max_queries // cols + 1):
            if cols * rows > max_queries:
                continue
            items = []
            valid = True
            for row in range(rows):
                ya = top + (bottom - top) * row / rows
                yb = top + (bottom - top) * (row + 1) / rows
                mid_y = (ya + yb) / 2
                for col in range(cols):
                    xa = left + (right - left) * col / cols
                    xb = left + (right - left) * (col + 1) / cols
                    mid_x = (xa + xb) / 2
                    lt, ln = y_to_lat(mid_y), x_to_lon(mid_x)
                    radius = max(distance_nm(lt, ln, y_to_lat(y), x_to_lon(x))
                                 for x in (xa, xb) for y in (ya, yb))
                    if radius > max_radius:
                        valid = False
                        break
                    items.append((lt, ln, max(5, min(max_radius, math.ceil(radius + 4)))))
                if not valid:
                    break
            if valid and (best is None or len(items) < len(best)):
                best = items
    if best is not None:
        return RadarCoverage(tuple(best), True,
                             (south, 360*left-180, north, 360*right-180), (lat, lon), farthest)
    # Deep zoom-out: don't issue 10s/100s of requests or silently pretend all
    # aircraft worldwide are present. Center-only and an explicit limited flag.
    return RadarCoverage(((lat, lon, max_radius),), False,
                         (south, 360*left-180, north, 360*right-180), (lat, lon), farthest)


def is_on_screen(lat, lon, bounds):
    south, west, north, east = bounds
    if not south <= lat <= north:
        return False
    # Find longitude equivalent in the unwrapped viewport interval.
    x = lon
    while x < west:
        x += 360
    while x > east and x - 360 >= west:
        x -= 360
    return west <= x <= east


def fit_trajectory(segments, width, height, *, padding=64, max_zoom=15, min_zoom=2):
    """Find a camera that fits every coordinate; safely handles 180° crossing."""
    coords = [(float(lat), float(lon)) for segment in segments for lat, lon in segment
              if math.isfinite(float(lat)) and math.isfinite(float(lon))]
    if not coords:
        return None
    xs = sorted(lon_to_x(lon_wrap(lon)) for _, lon in coords)
    ys = [lat_to_y(lat) for lat, _ in coords]
    # Find the largest empty longitude gap; the remaining arc is the shortest
    # arc spanning all track points (works for Pacific/dateline crossings).
    gaps = [((xs[(i+1) % len(xs)] + (1 if i == len(xs)-1 else 0)) - xs[i], i)
            for i in range(len(xs))]
    _, gap_at = max(gaps)
    first = xs[(gap_at + 1) % len(xs)]
    unwrapped = [x + (1 if x < first else 0) for x in xs]
    left, right = min(unwrapped), max(unwrapped)
    top, bottom = min(ys), max(ys)
    available_w = max(60, width - 2 * padding)
    available_h = max(60, height - 2 * padding)
    # Account for nonzero aircraft marker size with a small angular min span.
    dx = max(1e-8, right - left)
    dy = max(1e-8, bottom - top)
    level = min(math.log2(available_w / (TILE_SIZE * dx)),
                math.log2(available_h / (TILE_SIZE * dy)))
    level = max(min_zoom, min(max_zoom, level - .12))
    return y_to_lat((top + bottom) / 2), x_to_lon((left + right) / 2), level


def initial_bearing(lat1, lon1, lat2, lon2):
    """True initial bearing of a geodesic (degrees clockwise from North).

    The radar considers this only for consecutive plausible samples; otherwise
    the ADS-B ground track field is the authoritative presentation fallback.
    """
    a, b = math.radians(lat1), math.radians(lat2)
    delta = math.radians(lon_wrap(lon2 - lon1))
    x = math.sin(delta) * math.cos(b)
    y = math.cos(a) * math.sin(b) - math.sin(a) * math.cos(b) * math.cos(delta)
    return math.degrees(math.atan2(x, y)) % 360


def choose_buffered_coverage(lat, lon, zoom, width, height, *, preferred_area=4, max_queries=2):
    """Use the widest affordable buffer without increasing requests per refresh.

    A large-radius view can fall back to 2x/1x and may be partial on very wide
    zooms; never silently start a 6-query burst just because the user pans.
    """
    base = coverage_for_view(lat, lon, zoom, width, height, max_queries=max_queries)
    if not base.complete or preferred_area <= 1:
        return base, 1
    for area in ([4, 2] if preferred_area >= 4 else [2]):
        candidate = coverage_for_view(lat, lon, zoom, width, height,
                                      max_queries=max_queries, buffer_area=area)
        if candidate.complete and len(candidate.queries) <= len(base.queries):
            return candidate, area
    return base, 1


def viewport_within_coverage(view: RadarCoverage, fetched: RadarCoverage) -> bool:
    """Check whether the visible map rectangle is inside a fully fetched buffer.

    The rectangles are in unwrapped longitude. Allow shifting by ±360 degrees
    when a view moves across the international date line.
    """
    if not fetched.complete:
        return False
    s, w, n, e = view.bounds
    fs, fw, fn, fe = fetched.bounds
    if s < fs - 1e-7 or n > fn + 1e-7:
        return False
    return any(w + shift >= fw - 1e-7 and e + shift <= fe + 1e-7
               for shift in (-360, 0, 360))


def viewport_inside_radius(view: RadarCoverage, center: tuple[float, float],
                           radius_nm=250, reserve_nm=12) -> bool:
    """True only when every visible viewport corner lies within the cached circle.

    Bounds from the Mercator viewport may straddle the dateline; distance_nm
    handles those longitudes by wrapping the delta. Margins avoid churn when
    the user drags near the edge of the available ADS-B positions.
    """
    south, west, north, east = view.bounds
    if north - south >= 179 or east - west >= 360:
        return False
    return all(distance_nm(center[0], center[1], lat, lon) <= radius_nm - reserve_nm
               for lat in (south, north) for lon in (west, east))
