"""NOAA Aviation Weather Center METAR and SIGMET data sources.

No GTK imports here: requests, validation and GeoJSON processing can be tested
without a display.  Only requested weather products are fetched; METAR airport lookup is on demand.
"""
from __future__ import annotations
from .i18n import _

import json
from datetime import datetime, timezone
import math
import time
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

NOAA_ROOT = 'https://aviationweather.gov/api/data'
NOAA_CREDIT = 'https://aviationweather.gov/'
HTTP_TIMEOUT = 12


def get_json(url: str, *, limit=2_000_000):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'AeroScope/0.3.44 (+https://github.com/ehstbr/AeroScope; personal weather overlay)',
        'Accept': 'application/geo+json, application/json',
    })
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
        if getattr(response, 'status', 200) == 204:
            return None
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(_('Weather response exceeds safety size limit'))
    return json.loads(data)


def noaa_bbox(lat: float, lon: float, width_deg=7.0, height_deg=6.0):
    """Bounded, regional queries; avoid worldwide requests and the 400-item cap."""
    lat = max(-82., min(82., float(lat)))
    lon = max(-175., min(175., float(lon)))
    return (round(max(-89.0, lat-height_deg/2), 3),
            round(max(-179.9, lon-width_deg/2), 3),
            round(min(89.0, lat+height_deg/2), 3),
            round(min(179.9, lon+width_deg/2), 3))


def noaa_url(kind: str, bbox):
    if kind not in ('metar', 'sigmet'):
        raise ValueError(_('Invalid NOAA product'))
    bounds = ','.join(f'{v:.3f}' for v in bbox)
    return f'{NOAA_ROOT}/{kind}?' + urllib.parse.urlencode(
        {'bbox': bounds, 'format': 'geojson'})


def _float(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _features(payload):
    if not isinstance(payload, dict):
        return []
    if payload.get('type') == 'FeatureCollection':
        return payload.get('features', []) if isinstance(payload.get('features'), list) else []
    return [payload] if payload.get('type') == 'Feature' else []


@dataclass(frozen=True)
class Metar:
    station: str
    lat: float
    lon: float
    raw: str
    category: str
    observed: str
    # Decoded NOAA fields. Keep the original report untouched for specialists.
    details: dict | None = None


METAR_DETAIL_FIELDS = ('temp', 'dewp', 'wdir', 'wspd', 'wgst', 'visib',
                       'altim', 'clouds', 'wxString', 'vertVis')


def _metar_details(item):
    return {field: item[field] for field in METAR_DETAIL_FIELDS if field in item}


def display_metar_time(value) -> str:
    """NOAA can return an epoch (seconds/milliseconds) or an ISO-8601 date."""
    if value is None or value == '':
        return ''
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            epoch = float(value)
            if epoch > 100_000_000_000:  # millisecond timestamps
                epoch /= 1000
            return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
        if isinstance(value, str) and ('T' in value or value.endswith('Z')):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
    except (OverflowError, ValueError, OSError, TypeError):
        pass
    return str(value)[:40]


def parse_metars(payload):
    """Accept NOAA GeoJSON and its equivalent structured JSON station rows."""
    result = []
    # NOAA GeoJSON is the requested format; the JSON fallback is compatible
    # with data returned by individual station requests and older endpoints.
    entries = payload[:400] if isinstance(payload, list) else _features(payload)[:400]
    for feature in entries:
        if not isinstance(feature, dict):
            continue
        if isinstance(feature.get('geometry'), dict):
            geom = feature['geometry']
            props = feature.get('properties') or {}
            if geom.get('type') != 'Point' or not isinstance(props, dict):
                continue
            coordinates = geom.get('coordinates', [])
            if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
                continue
            lon, lat = _float(coordinates[0]), _float(coordinates[1])
        else:
            props = feature
            lon, lat = _float(props.get('lon')), _float(props.get('lat'))
        if lon is None or lat is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        station = str(props.get('icaoId') or props.get('station') or
                      props.get('id') or props.get('station_id') or '').strip().upper()[:9]
        if not station:
            continue
        result.append(Metar(station, lat, lon,
                            str(props.get('rawOb') or props.get('raw_text') or props.get('raw') or '').strip()[:600],
                            str(props.get('fltCat') or props.get('flight_category') or 'N/D').upper()[:8],
                            display_metar_time(props.get('obsTime') or props.get('observation_time')),
                            _metar_details(props)))
    return result


@dataclass(frozen=True)
class Sigmet:
    name: str
    rings: tuple[tuple[tuple[float, float], ...], ...]  # lat,lon for each ring
    text: str
    metadata: dict | None = None  # original NOAA properties for validity/qualifiers


def parse_sigmets(payload):
    result = []
    for feature in _features(payload)[:250]:
        if not isinstance(feature, dict):
            continue
        props = feature.get('properties') or {}
        geom = feature.get('geometry') or {}
        if not isinstance(props, dict) or not isinstance(geom, dict):
            continue
        geometry = geom.get('type')
        coords = geom.get('coordinates', [])
        polygons = [coords] if geometry == 'Polygon' else (coords if geometry == 'MultiPolygon' else [])
        rings = []
        for polygon in polygons[:5]:
            if not isinstance(polygon, list):
                continue
            for ring in polygon[:1]:  # outer boundary only; avoid painting holes as weather
                if not isinstance(ring, list):
                    continue
                pts = []
                for coord in ring[:250]:
                    if not isinstance(coord, list) or len(coord) < 2:
                        continue
                    lon, lat = _float(coord[0]), _float(coord[1])
                    if lon is not None and lat is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                        pts.append((lat, lon))
                if len(pts) >= 3:
                    rings.append(tuple(pts))
        if rings:
            kind = str(props.get('hazard') or props.get('phenomenon') or
                       props.get('sigmetType') or 'SIGMET').strip()[:50]
            text = str(props.get('rawSigmet') or props.get('raw') or
                       props.get('rawAirSigmet') or props.get('description') or '')[:1200]
            result.append(Sigmet(kind, tuple(rings), text, dict(props)))
    return result


def fetch_sigmets_bbox(bbox):
    """Advisories for a bounded region (independent of visible map layers)."""
    return parse_sigmets(get_json(noaa_url('sigmet', bbox)))


def fetch_noaa(lat, lon, *, metar=True, sigmet=True):
    bbox = noaa_bbox(lat, lon)
    return (parse_metars(get_json(noaa_url('metar', bbox))) if metar else [],
            parse_sigmets(get_json(noaa_url('sigmet', bbox))) if sigmet else [])


def fetch_noaa_with_errors(lat, lon, *, metar=True, sigmet=True):
    """Independent NOAA products; one failing must not hide the other."""
    bbox = noaa_bbox(lat, lon)
    errors = {}
    metars, sigmets = [], []
    if metar:
        try:
            metars = parse_metars(get_json(noaa_url('metar', bbox)))
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TypeError) as exc:
            errors['metar'] = str(exc)
    if sigmet:
        try:
            sigmets = parse_sigmets(get_json(noaa_url('sigmet', bbox)))
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TypeError) as exc:
            errors['sigmet'] = str(exc)
    return metars, sigmets, errors


def known_airport_icaos_for_bbox(bbox):
    """ICAO identifiers for airport markers in the current regional sample.

    The IATA chip shown on a map is *not* the station identifier used by NOAA:
    PLU -> SBBH and CNF -> SBCF, for example. Only include stations within
    the bounded regional bbox; do not turn a local overlay into a global poll.
    """
    from .data import AIRPORTS
    south, west, north, east = bbox
    codes = {icao for icao, _name, lat, lon in AIRPORTS.values()
             if south <= lat <= north and west <= lon <= east}
    return sorted(codes)


def fetch_metar_stations(stations, *, fallback_positions=None):
    """One NOAA request for known ICAOs; never one HTTP request per airport.

    NOAA supports a comma-separated ids parameter. It may omit a station when
    it has no *current* observation; absence must not be shown as VFR.
    """
    codes = sorted({str(code).strip().upper() for code in stations})
    if not codes:
        return []
    if len(codes) > 50 or any(not re.fullmatch(r'[A-Z0-9]{4}', c) for c in codes):
        raise ValueError(_('Invalid METAR station list'))
    url = NOAA_ROOT + '/metar?' + urllib.parse.urlencode({
        'ids': ','.join(codes), 'format': 'json'})
    payload = get_json(url, limit=600_000)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError(_('Unexpected regional METAR response'))
    # Do not trust an out-of-scope station even if the provider includes it.
    allowed = set(codes)
    results = {metar.station: metar for metar in parse_metars(payload)
               if metar.station in allowed}
    # Some station rows can contain a valid observation without coordinates.
    # For *known* ICAO airports, reuse our verified static airport position;
    # the reported meteorological fields still come exclusively from NOAA.
    from .data import AIRPORTS
    positions = {info[0]: (info[2], info[3]) for info in AIRPORTS.values()}
    # A bookmarked NOAA station may legitimately omit coordinates in an API
    # response; use the location originally observed and saved by the user.
    for station, point in (fallback_positions or {}).items():
        try:
            lat, lon = float(point[0]), float(point[1])
            if station in allowed and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
                positions[station] = (lat, lon)
        except (ValueError, TypeError, IndexError):
            continue
    for item in payload:
        if not isinstance(item, dict):
            continue
        code = str(item.get('icaoId') or '').strip().upper()
        if code not in allowed or code in results or code not in positions:
            continue
        raw = str(item.get('rawOb') or '').strip()[:600]
        if not raw and not _metar_details(item):
            continue  # a station record is not necessarily an observation
        lat, lon = positions[code]
        results[code] = Metar(code, lat, lon, raw,
                              str(item.get('fltCat') or 'N/D').upper()[:8],
                              display_metar_time(item.get('obsTime')), _metar_details(item))
    return list(results.values())


def fetch_metar_station(icao):
    """METAR by airport ICAO, on demand even with map overlay disabled."""
    station = str(icao).strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{4}', station):
        raise ValueError(_('Invalid ICAO code'))
    url = NOAA_ROOT + '/metar?' + urllib.parse.urlencode({'ids':station,'format':'json'})
    data = get_json(url, limit=100_000)
    if data is None:
        return None
    if not isinstance(data, list):
        raise ValueError(_('Unexpected METAR response'))
    for item in data:
        if not isinstance(item, dict) or str(item.get('icaoId') or '').upper() != station:
            continue
        observed = display_metar_time(item.get('obsTime'))
        return Metar(station, _float(item.get('lat')) or 0., _float(item.get('lon')) or 0.,
                     str(item.get('rawOb') or '').strip()[:600],
                     str(item.get('fltCat') or 'N/D').upper()[:8], observed,
                     _metar_details(item))
    return None
