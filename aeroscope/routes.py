"""Probable ADSB.lol origin/destination pairs and great-circle map geometry.

The ADS-B aircraft feed does NOT transmit a flight plan. A routeset association
is metadata and its great-circle is only a *geographic reference*, not a route
of waypoints, an ATC clearance, or a confirmed flown trajectory.

This module has no GTK dependency so it is unit-testable headlessly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import time


@dataclass(frozen=True)
class RouteAirport:
    code: str
    icao: str
    name: str
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class ProbableRoute:
    callsign: str
    origin: RouteAirport
    destination: RouteAirport
    plausible: bool | None = None


def _coordinate(value, minimum, maximum):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and minimum <= number <= maximum else None


def _airport(value, code_hint='', known=None):
    """Resolve the route metadata conservatively, never invent coordinates."""
    if isinstance(value, str):
        value = {'icao': value} if len(value.strip()) == 4 else {'iata': value}
    if not isinstance(value, dict):
        value = {}
    code = str(value.get('iata') or value.get('icao') or value.get('code') or code_hint).strip().upper()
    icao = str(value.get('icao') or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{3,4}', code):
        return None
    lat = _coordinate(value.get('lat', value.get('latitude')), -85, 85)
    lon = _coordinate(value.get('lon', value.get('lng', value.get('longitude'))), -180, 180)
    if (lat is None or lon is None) and known:
        fallback = known.get(code) or known.get(icao)
        if fallback is not None:
            icao = icao or fallback[0]
            lat, lon = fallback[2], fallback[3]
            name = str(value.get('name') or fallback[1])[:140]
            return RouteAirport(code, icao, name, lat, lon)
    # Some records supply codes but no geocoordinates. Preserve the actual
    # association so the UI can show origin/destination without drawing a line.
    # Reject explicitly invalid coordinates rather than inventing a location.
    if ('lat' in value or 'latitude' in value or 'lon' in value or 'lng' in value
            or 'longitude' in value) and (lat is None or lon is None):
        return None
    name = str(value.get('name') or value.get('location') or code).strip()[:140]
    return RouteAirport(code, icao, name, lat, lon)


def _entries(payload):
    """The public v0 endpoint is documented as returning JSON encoded string;
    providers also return arrays and dict wrappers across deployments.
    """
    import json
    for _ in range(2):
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                return []
        else:
            break
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for field in ('routes', 'planes', 'data', 'results'):
            if isinstance(payload.get(field), list):
                return payload[field]
        if 'callsign' in payload:
            return [payload]
    return []


def parse_routeset(payload, callsign: str, known=None) -> ProbableRoute | None:
    """Accept documented routeset variants, only for the exact callsign.

    An incomplete airport code is not silently converted into a geographic
    location. `known` may provide verified coordinates from the local catalog.
    """
    requested = str(callsign).strip().upper()
    for item in _entries(payload):
        if not isinstance(item, dict):
            continue
        item_call = str(item.get('callsign') or item.get('flight') or '').strip().upper()
        if item_call != requested:
            continue
        airports = item.get('_airports') or item.get('airports')
        candidates = airports if isinstance(airports, list) else []
        code_string = str(item.get('_airport_codes_iata') or item.get('airport_codes') or '')
        code_pair = [x.strip().upper() for x in code_string.split('-')]
        if len(candidates) < 2:
            origin_raw = item.get('origin') or item.get('from')
            dest_raw = item.get('destination') or item.get('to')
            if origin_raw and dest_raw:
                candidates = [origin_raw, dest_raw]
        if len(candidates) < 2 and len(code_pair) == 2:
            candidates = code_pair
        if len(candidates) < 2:
            continue
        first_hint = code_pair[0] if len(code_pair) == 2 else ''
        last_hint = code_pair[1] if len(code_pair) == 2 else ''
        first = _airport(candidates[0], first_hint, known)
        last = _airport(candidates[-1], last_hint, known)
        if first is None or last is None or first.code == last.code:
            continue
        if (first.lat is not None and last.lat is not None
                and (first.lat, first.lon) == (last.lat, last.lon)):
            continue
        plausible = item.get('plausible')
        return ProbableRoute(requested, first, last,
                             plausible if isinstance(plausible, bool) else None)
    return None


def route_has_geometry(route: ProbableRoute | None) -> bool:
    return bool(route and all(isinstance(v, (int, float)) and math.isfinite(v)
                              for v in (route.origin.lat, route.origin.lon,
                                        route.destination.lat, route.destination.lon)))


def great_circle_points(lat1, lon1, lat2, lon2, count=90):
    """Shortest surface path between airports, with geodesic sampling.

    The result is geographic only; it never represents aircraft waypoints.
    """
    count = max(2, min(180, int(count)))
    a1, o1, a2, o2 = map(math.radians, (lat1, lon1, lat2, lon2))
    p = (math.cos(a1)*math.cos(o1), math.cos(a1)*math.sin(o1), math.sin(a1))
    q = (math.cos(a2)*math.cos(o2), math.cos(a2)*math.sin(o2), math.sin(a2))
    dot = max(-1., min(1., sum(u*v for u,v in zip(p,q))))
    theta = math.acos(dot)
    result = []
    for index in range(count+1):
        t = index/count
        if theta < 1e-10:
            xyz = p
        elif abs(math.pi-theta) < 1e-7:
            # Antipodal endpoints are ambiguous: simple normalized blend
            # avoids division by sin(pi). This case is extremely rare.
            xyz = [((1-t)*p[i] + t*q[i]) for i in range(3)]
            mag = math.sqrt(sum(z*z for z in xyz))
            if mag < 1e-9:
                xyz = p
            else:
                xyz = [z/mag for z in xyz]
        else:
            s1 = math.sin((1-t)*theta)/math.sin(theta)
            s2 = math.sin(t*theta)/math.sin(theta)
            xyz = [s1*p[i]+s2*q[i] for i in range(3)]
        lat = math.degrees(math.atan2(xyz[2], math.hypot(xyz[0], xyz[1])))
        lon = (math.degrees(math.atan2(xyz[1], xyz[0]))+180)%360-180
        result.append((lat, lon))
    result[0], result[-1] = (float(lat1), float(lon1)), (float(lat2), float(lon2))
    return result


def map_segments(points):
    """Separate date-line crossings: never draw a 360-degree horizontal chord."""
    segments = []
    current = []
    for lat, lon in points:
        if current and abs(lon-current[-1][1]) > 180:
            if len(current) > 1:
                segments.append(current)
            current = []
        current.append((lat, lon))
    if len(current) > 1:
        segments.append(current)
    return segments


class RouteCache:
    """In-memory cache per aircraft+callsign. Failures have short TTL."""
    def __init__(self, success_ttl=1800, miss_ttl=120):
        self.success_ttl = success_ttl
        self.miss_ttl = miss_ttl
        self._values = {}

    def get(self, key):
        entry = self._values.get(key)
        if entry is None:
            return False, None, None
        expires, value, error = entry
        if time.monotonic() >= expires:
            self._values.pop(key, None)
            return False, None, None
        return True, value, error

    def put(self, key, route, error=None):
        ttl = self.success_ttl if route is not None else self.miss_ttl
        self._values[key] = (time.monotonic()+ttl, route, str(error) if error else None)

    def remove(self, key):
        self._values.pop(key, None)

    def clear(self):
        self._values.clear()
