"""Fast, reusable Web-Mercator geometry for AeroScope SIGMET outlines.

Pure Python, independent of Gtk, Libshumate and the NOAA networking layer.
NOAA rings are *never* altered in the source data: simplification applies to
screen rendering only. Geographic hit testing still uses the original rings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from .sigmet_style import classify_sigmet, SigmetStyle

_MAX_LAT = 85.05112878


def project(lat: float, lon: float) -> tuple[float, float]:
    """Global Web-Mercator coordinates normalized to a 1x1 world."""
    lat = max(-_MAX_LAT, min(_MAX_LAT, float(lat)))
    x = (float(lon) + 180.0) / 360.0
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2
    return x, y


def _unwrap(points):
    result = []
    previous = None
    for x, y in points:
        if previous is not None:
            x += round(previous - x)
        result.append((x, y))
        previous = x
    return tuple(result)


def _sq_dist_point_segment(p, a, b):
    x, y = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return (x - ax) ** 2 + (y - ay) ** 2
    t = max(0., min(1., ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return (x - ax - dx * t) ** 2 + (y - ay - dy * t) ** 2


def simplify_path(points, tolerance):
    """Iterative Ramer-Douglas-Peucker; endpoints are retained."""
    points = tuple(points)
    n = len(points)
    if n <= 2 or tolerance <= 0:
        return points
    # A cheap radial-distance pass reduces NOAA coastlike outlines before
    # the more expensive RDP scan. Use 45% of the final pixel tolerance so
    # the additional approximation stays sub-pixel at most common zooms.
    if n > 12:
        radial_sq = (tolerance * .45) ** 2
        sparse = [points[0]]
        for candidate in points[1:-1]:
            if ((candidate[0] - sparse[-1][0]) ** 2 +
                    (candidate[1] - sparse[-1][1]) ** 2 > radial_sq):
                sparse.append(candidate)
        sparse.append(points[-1])
        points = tuple(sparse)
        n = len(points)
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    sq_tol = tolerance * tolerance
    while stack:
        start, end = stack.pop()
        a, b = points[start], points[end]
        best_i, best_d = None, sq_tol
        for i in range(start + 1, end):
            d = _sq_dist_point_segment(points[i], a, b)
            if d > best_d:
                best_i, best_d = i, d
        if best_i is not None:
            keep.add(best_i)
            stack.extend(((start, best_i), (best_i, end)))
    return tuple(points[i] for i in sorted(keep))


def _bounds(points):
    return (min(x for x, _ in points), min(y for _, y in points),
            max(x for x, _ in points), max(y for _, y in points))


def overlaps(bounds, view):
    """Axis-aligned bbox intersection, inclusive at the edges."""
    return (bounds[2] >= view[0] and bounds[0] <= view[2]
            and bounds[3] >= view[1] and bounds[1] <= view[3])


@dataclass
class Ring:
    coords: tuple[tuple[float, float], ...]
    bbox: tuple[float, float, float, float]
    _cache: dict[tuple[int, int], tuple[tuple[float, float], ...]] = field(default_factory=dict)

    def at_zoom(self, zoom: float, tile_size=256, pixel_tolerance=1.3):
        # floor is safe: lower-zoom simplification is used for the whole
        # fractional-zoom segment; the loss is at most ~2.6 screen pixels.
        bucket = max(0, min(20, int(math.floor(zoom))))
        key = (bucket, int(round(tile_size)))
        if key not in self._cache:
            tol = pixel_tolerance / (tile_size * 2 ** bucket)
            base = self.coords
            # SIGMET borders are closed and may have 1000+ source vertices.
            # Simplify the open run, then restore a closed loop.
            closed = len(base) > 2 and base[0] == base[-1]
            open_coords = base[:-1] if closed else base
            simplified = simplify_path(open_coords, tol)
            if len(simplified) < 3 and len(open_coords) >= 3:
                simplified = open_coords[:3]
            self._cache[key] = (simplified + (simplified[0],)
                                   if closed and simplified else simplified)
            # Limit per-ring caches if the user explores many zoom levels.
            if len(self._cache) > 4:
                self._cache.pop(next(iter(self._cache)))
        return self._cache[key]


@dataclass
class AdvisoryShape:
    advisory: object
    rings: tuple[Ring, ...]
    bbox: tuple[float, float, float, float]
    marker: tuple[float, float] | None
    style: SigmetStyle  # cached once per NOAA report, not reclassified per frame


def prepare_sigmets(sigmets, marker_locator=None, *, previous=()):
    """Prepare NOAA scene, reusing geometry/cache for unchanged boundaries.

    An unchanged bulletin reuses the entire shape and its zoom caches. When
    only metadata changes, the associated NOAA bulletin is replaced while its
    exact geographic contour and cached simplification are preserved.
    """
    by_geometry = {shape.advisory.rings: shape for shape in previous}
    result = []
    for advisory in sigmets:
        old = by_geometry.get(advisory.rings)
        if old is not None:
            result.append(old if old.advisory == advisory else
                          AdvisoryShape(advisory, old.rings, old.bbox, old.marker,
                                        classify_sigmet(advisory)))
            continue
        rings = []
        for source_ring in getattr(advisory, 'rings', ()):
            try:
                coords = _unwrap(project(lat, lon) for lat, lon in source_ring)
            except (ValueError, TypeError, OverflowError):
                continue
            if len(coords) >= 3 and all(math.isfinite(p) for xy in coords for p in xy):
                rings.append(Ring(coords, _bounds(coords)))
        if rings:
            bbox = (min(r.bbox[0] for r in rings), min(r.bbox[1] for r in rings),
                    max(r.bbox[2] for r in rings), max(r.bbox[3] for r in rings))
            point = marker_locator(advisory.rings) if marker_locator else None
            result.append(AdvisoryShape(advisory, tuple(rings), bbox, point,
                                        classify_sigmet(advisory)))
    return tuple(result)


def viewport_bounds(center_x, center_y, width, height, scale, padding=48):
    half_x = (width / 2 + padding) / scale
    half_y = (height / 2 + padding) / scale
    return center_x - half_x, center_y - half_y, center_x + half_x, center_y + half_y


def scene_visible(shapes, bounds):
    """Only submit on-screen advisories/rings (including a safety margin)."""
    result = []
    cx = (bounds[0] + bounds[2]) / 2
    for shape in shapes:
        # NOAA polygons can cross the ±180° dateline; choose nearest copy.
        shift = round(cx - (shape.bbox[0] + shape.bbox[2]) / 2)
        rect = (shape.bbox[0] + shift, shape.bbox[1],
                shape.bbox[2] + shift, shape.bbox[3])
        if not overlaps(rect, bounds):
            continue
        visible_rings = tuple((ring, shift) for ring in shape.rings
                              if overlaps((ring.bbox[0] + shift, ring.bbox[1],
                                           ring.bbox[2] + shift, ring.bbox[3]), bounds))
        if visible_rings:
            result.append((shape, visible_rings))
    return result
