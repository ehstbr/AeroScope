"""API ADSB.lol, normalização de aeronaves e geocodificação.

Sem dependência de GTK para permitir testes automatizados independentes da UI.
"""
from __future__ import annotations
from .i18n import _
import json
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from .routes import parse_routeset, ProbableRoute
from .playback import parse_historical_replay

AGENT = 'AeroScope/0.3.16 (+https://github.com/ehstbr/Aeroscope; recreational GNOME aircraft map)'
API = 'https://api.adsb.lol/v2'
CITY_API = 'https://geocoding-api.open-meteo.com/v1/search'
IP_GEO_API = 'https://ipwho.is/'  # User-initiated only; no account or API key

# Referências locais: os demais locais podem ser pesquisados via Open-Meteo.
AIRPORTS = {
    'CNF': ('SBCF', 'Belo Horizonte / Confins', -19.6244, -43.9719),
    'PLU': ('SBBH', 'Belo Horizonte / Pampulha', -19.8512, -43.9506),
    'DIQ': ('SNDV', 'Divinópolis', -20.1807, -44.8704),
    'GRU': ('SBGR', 'São Paulo / Guarulhos', -23.4356, -46.4731),
    'CGH': ('SBSP', 'São Paulo / Congonhas', -23.6261, -46.6566),
    'VCP': ('SBKP', 'Campinas / Viracopos', -23.0074, -47.1345),
    'GIG': ('SBGL', 'Rio de Janeiro / Galeão', -22.8090, -43.2506),
    'SDU': ('SBRJ', 'Rio de Janeiro / Santos Dumont', -22.9105, -43.1631),
    'BSB': ('SBBR', 'Brasília', -15.8697, -47.9208),
    'SSA': ('SBSV', 'Salvador', -12.9086, -38.3225),
    'REC': ('SBRF', 'Recife', -8.1265, -34.9236),
    'FOR': ('SBFZ', 'Fortaleza', -3.7763, -38.5326),
    'NAT': ('SBSG', 'Natal', -5.7681, -35.3761),
    'MCZ': ('SBMO', 'Maceió', -9.5108, -35.7917),
    'CWB': ('SBCT', 'Curitiba', -25.5317, -49.1758),
    'POA': ('SBPA', 'Porto Alegre', -29.9944, -51.1714),
    'FLN': ('SBFL', 'Florianópolis', -27.6703, -48.5525),
    'NVT': ('SBNF', 'Navegantes', -26.8794, -48.6514),
    'IGU': ('SBFI', 'Foz do Iguaçu', -25.5942, -54.4894),
    'GYN': ('SBGO', 'Goiânia', -16.6319, -49.2207),
    'CGB': ('SBCY', 'Cuiabá', -15.6529, -56.1167),
    'CGR': ('SBCG', 'Campo Grande', -20.4687, -54.6725),
    'MAO': ('SBEG', 'Manaus', -3.0386, -60.0497),
    'BEL': ('SBBE', 'Belém', -1.3793, -48.4763),
    'SLZ': ('SBSL', 'São Luís', -2.5866, -44.2361),
    'THE': ('SBTE', 'Teresina', -5.0599, -42.8235),
    'JPA': ('SBJP', 'João Pessoa', -7.1458, -34.9486),
    'VIX': ('SBVT', 'Vitória', -20.2581, -40.2864),
    'BPS': ('SBPS', 'Porto Seguro', -16.4386, -39.0809),
    'UDI': ('SBUL', 'Uberlândia', -18.8836, -48.2253),
    'MOC': ('SBMK', 'Montes Claros', -16.7069, -43.8189),
    'JDF': ('SBJF', 'Juiz de Fora', -21.7915, -43.3868),
    'LDB': ('SBLO', 'Londrina', -23.3336, -51.1301),
    'MGA': ('SBMG', 'Maringá', -23.4794, -52.0122),
    'RAO': ('SBRP', 'Ribeirão Preto', -21.1343, -47.7742),
    'SJP': ('SBSR', 'São José do Rio Preto', -20.8166, -49.4065),
    'PMW': ('SBPJ', 'Palmas', -10.2915, -48.3570),
    'LIS': ('LPPT', 'Lisboa', 38.7742, -9.1342),
    'OPO': ('LPPR', 'Porto', 41.2481, -8.6814),
    'MIA': ('KMIA', 'Miami', 25.7954, -80.2901),
    'MCO': ('KMCO', 'Orlando', 28.4312, -81.3081),
    'JFK': ('KJFK', 'Nova York / JFK', 40.6413, -73.7781),
    'LHR': ('EGLL', 'Londres / Heathrow', 51.4700, -0.4543),
    'CDG': ('LFPG', 'Paris / Charles de Gaulle', 49.0097, 2.5479),
}


@dataclass
class Aircraft:
    hex: str
    flight: str
    registration: str
    model: str
    lat: float
    lon: float
    altitude_ft: float | None
    speed_kts: float | None
    track: float
    vertical_rate: float | None
    seen: float
    source: str = 'adsb_icao'
    squawk: str = ''
    emergency: str = ''
    on_ground: bool | None = None  # explicit ADS-B ground indication when available

    @property
    def altitude(self):
        return 'Solo' if self.altitude_ft is None else _('{value0:,} feet').format(value0=round(self.altitude_ft)).replace(',', '.')

    @property
    def speed(self):
        return '—' if self.speed_kts is None else f'{round(self.speed_kts * 1.852)} km/h'


class RateLimitError(RuntimeError):
    """Provider replied HTTP 429; the UI must back off."""
    def __init__(self, message, retry_after=120):
        super().__init__(message)
        self.retry_after = max(30, min(900, int(retry_after)))


def read_json(url: str, timeout: int = 12, max_bytes: int = 3_000_000) -> dict:
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as res:
            content = res.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise RuntimeError(_('Response exceeds the safe size limit.'))
            return json.loads(content.decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry = e.headers.get('Retry-After', '120') if e.headers else '120'
            retry = int(retry) if str(retry).isdigit() else 120
            raise RateLimitError(_('Request limit (HTTP 429). Updates temporarily paused.'), retry_after=retry) from e
        raise RuntimeError(_('API unavailable (HTTP {value0}).').format(value0=e.code)) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(_('Cannot connect to service: {value0}').format(value0=getattr(e, 'reason', str(e)))) from e
    except (UnicodeError, ValueError) as e:
        raise RuntimeError(_('The API returned invalid data.')) from e


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        val = float(value)
    except (ValueError, TypeError):
        return None
    return val if math.isfinite(val) else None


def parse_aircraft(payload: dict) -> list[Aircraft]:
    found = []
    for row in payload.get('ac', []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict):
            continue
        lat, lon = _number(row.get('lat')), _number(row.get('lon'))
        if lat is None or lon is None or not (-85 <= lat <= 85 and -180 <= lon <= 180):
            continue
        seen = _number(row.get('seen_pos'))
        if seen is not None and seen > 90:
            continue
        code = str(row.get('hex') or '').strip().lower()
        if not code:
            continue
        alt = _number(row.get('alt_baro'))
        found.append(Aircraft(
            hex=code, flight=str(row.get('flight') or '').strip(),
            registration=str(row.get('r') or '').strip(),
            model=str(row.get('t') or '').strip(), lat=lat, lon=lon,
            altitude_ft=alt, speed_kts=_number(row.get('gs')),
            track=_number(row.get('track')) or 0.0,
            vertical_rate=_number(row.get('baro_rate')),
            seen=seen if seen is not None else 0,
            source=str(row.get('type') or 'adsb_icao'),
            squawk=str(row.get('squawk') or '').strip(),
            emergency=str(row.get('emergency') or '').strip().lower(),
            on_ground=(True if row.get('alt_baro') == 'ground' or
                       row.get('on_ground') is True or row.get('ground') is True
                       else False if row.get('on_ground') is False or row.get('ground') is False
                       else None),
        ))
    return found


def fetch_area(lat: float, lon: float, radius_nm: int) -> list[Aircraft]:
    if not (-85 <= lat <= 85 and -180 <= lon <= 180 and 1 <= radius_nm <= 250):
        raise ValueError(_('Invalid coordinates or radius'))
    return parse_aircraft(read_json(f'{API}/lat/{lat:.5f}/lon/{lon:.5f}/dist/{radius_nm}'))


def fetch_visible_area(queries):
    """Fetch each bounded view circle and deduplicate ICAO24 across overlaps.

    No server-side storage or concurrent request flood. Partial errors surface
    only when every subquery fails; a partial viewport is labelled by the GUI.
    """
    if not 1 <= len(queries) <= 6:
        raise ValueError(_('Invalid coverage request count'))
    merged = {}
    successful = 0
    first_error = None
    for lat, lon, radius_nm in queries:
        try:
            for plane in fetch_area(lat, lon, radius_nm):
                old = merged.get(plane.hex)
                if old is None or plane.seen < old.seen:
                    merged[plane.hex] = plane
            successful += 1
        except RateLimitError:
            # Do not keep querying the remaining circles after the provider
            # explicitly throttles us. The UI applies a longer backoff.
            raise
        except (RuntimeError, OSError) as exc:
            if first_error is None:
                first_error = str(exc)
    if not successful:
        raise RuntimeError(first_error or _('The network did not respond to requests.'))
    return list(merged.values()), successful, len(queries)


def fetch_plane(kind: str, term: str) -> list[Aircraft]:
    allowed = {'callsign', 'registration', 'hex'}
    if kind not in allowed or not re.fullmatch(r'[A-Za-z0-9\-]{2,12}', term):
        raise ValueError(_('Invalid search'))
    return parse_aircraft(read_json(f'{API}/{kind}/{urllib.parse.quote(term.upper())}'))


def geocode_city(q: str):
    if not (2 <= len(q.strip()) <= 90):
        raise ValueError(_('Enter at least two characters'))
    params = urllib.parse.urlencode({'name': q.strip(), 'count': 6, 'language': 'pt', 'format': 'json'})
    data = read_json(f'{CITY_API}?{params}')
    return [(str(x.get('name', '')), str(x.get('admin1', '')), str(x.get('country', '')),
             float(x['latitude']), float(x['longitude']))
            for x in data.get('results', []) if 'latitude' in x and 'longitude' in x]


def geolocate_by_public_ip() -> tuple[float, float, str]:
    """Approximate location by public network IP, ONLY after explicit user consent.

    The service sees the public IP in the HTTPS request; no IP address is
    requested explicitly, persisted, displayed or logged by AeroScope.
    Geolocation may reflect the ISP/VPN endpoint instead of the device.
    """
    payload = read_json(IP_GEO_API, timeout=10)
    if not isinstance(payload, dict) or payload.get('success') is not True:
        msg = payload.get('message', '') if isinstance(payload, dict) else ''
        raise RuntimeError(_('IP location unavailable: {value0}').format(value0=str(msg)[:120] or _('service did not return a valid response')))
    lat, lon = _number(payload.get('latitude')), _number(payload.get('longitude'))
    if lat is None or lon is None or not (-85 <= lat <= 85 and -180 <= lon <= 180):
        raise RuntimeError(_('Location service returned invalid coordinates.'))
    city = str(payload.get('city') or '').strip()[:80]
    region = str(payload.get('region') or '').strip()[:80]
    country = str(payload.get('country') or '').strip()[:80]
    place = ', '.join([x for x in (city, region, country) if x]) or _('Approximate location')
    return lat, lon, place


def airport_board_url(iata: str) -> str:
    """Read-only public airport page, not an API or flight schedule stored here."""
    key = iata.strip().upper()
    if key not in AIRPORTS:
        raise ValueError(_('Airport not in catalog'))
    return f'https://www.flightradar24.com/data/airports/{key.lower()}'


def find_airport(text: str):
    key = text.strip().upper()
    for iata, data in AIRPORTS.items():
        if key in (iata, data[0]):
            return iata, data
    return None


def demo_aircraft(lat: float, lon: float, tick: int = 0):
    planes = []
    ids = [('GLO1732', 'PR-GTL', 'B738', 31200, 445, 86),
           ('AZU4812', 'PR-YRK', 'E195', 27500, 390, 218),
           ('TAM3320', 'PR-MHU', 'A320', 34800, 461, 162),
           ('PT-ABC', 'PT-ABC', 'C172', 5200, 115, 42),
           ('GLO1549', 'PR-GXX', 'B38M', 37000, 470, 290),
           ('AZU6600', 'PS-VIH', 'E295', 35100, 455, 16),
           ('PT-LLA', 'PT-LLA', 'R44', 1800, 80, 331),
           ('TAM3441', 'PR-MHN', 'A319', 30100, 420, 265)]
    for i, (flight, reg, model, alt, speed, track) in enumerate(ids):
        rad = math.radians((i * 137.5) % 360)
        distance = 0.30 + (i % 4) * .16
        # Simulação explicitamente identificada: a posição muda somente por atualização.
        lat2 = lat + math.cos(rad) * distance + tick * math.cos(math.radians(track)) * .014
        lon2 = lon + math.sin(rad) * distance + tick * math.sin(math.radians(track)) * .014
        planes.append(Aircraft(f'{0xa00064+i:x}', flight, reg, model,
                                lat2, lon2, alt, speed, track, 0, 0,
                                squawk=('7700' if i == 0 else '7600' if i == 6 else ''),
                                emergency=('general' if i == 0 else 'nordo' if i == 6 else 'none')))
    return planes

# Optional, on-demand enrichment: no key, no background crawling.
AERO_API = 'https://adsb.aero/api/v1'
PHOTO_API = 'https://api.planespotters.net/pub/photos'
PHOTO_IMAGE_HOSTS = frozenset({'cdn.planespotters.net', 'cdn.plnspttrs.net', 'www.planespotters.net'})
PHOTO_LOG = logging.getLogger('aeroscope.photos')


def _photo_url(url: str, *, page: bool = False) -> str | None:
    """Allow only trusted Planespotters HTTPS domains, including their CDNs.

    Supports protocol-relative URLs from the API while rejecting embedded
    credentials, custom ports and suffix lookalikes (e.g. evilplanespotters.net).
    """
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    if url.startswith('//'):
        url = 'https:' + url
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    allowed = (
        host in ('planespotters.net', 'plnspttrs.net')
        or host.endswith('.planespotters.net')
        or host.endswith('.plnspttrs.net')
    )
    try:
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != 'https' or not allowed or parsed.username or parsed.password
            or port not in (None, 443)):
        return None
    if page and not (host == 'planespotters.net' or host == 'www.planespotters.net'):
        return None
    return url


def _post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={
        'User-Agent': 'AeroScope/0.2 (+https://github.com/ehstbr/Aeroscope)',
        'Accept': 'application/json', 'Content-Type': 'application/json',
    }, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(4_000_000).decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(_('ADSB.aero history is unavailable.')) from exc


def fetch_live_route(callsign: str, lat: float, lon: float) -> ProbableRoute | None:
    """Origin/destination association; queried ONLY on aircraft selection.

    The payload is not an actual ATC flight plan. Never re-label the proposed
    great-circle as a real or scheduled flight path.
    """
    callsign = str(callsign).strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{2,12}', callsign):
        return None
    if not (-85 <= lat <= 85 and -180 <= lon <= 180):
        raise ValueError(_('Invalid coordinates for route lookup'))
    url = 'https://api.adsb.lol/api/0/routeset'
    body = json.dumps({'planes': [{'callsign': callsign, 'lat': round(lat, 5),
                                   'lng': round(lon, 5)}]}, separators=(',', ':')).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={
        'User-Agent': AGENT, 'Accept': 'application/json',
        'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=12) as res:
            # The provider sometimes returns an empty or non-JSON body despite
            # a successful HTTP status. Do not turn that into an opaque
            # JSONDecodeError in the user's terminal (or invent endpoints).
            if getattr(res, 'status', 200) == 204:
                return None  # Documented no-content semantics, not a failure.
            raw = res.read(500_001)
            if len(raw) > 500_000:
                raise RuntimeError(_('Route provider response is too large.'))
            if not raw.strip():
                raise RuntimeError(_('Route provider returned an empty response. Try again later.'))
            try:
                payload = json.loads(raw.decode('utf-8'))
            except (ValueError, UnicodeError) as exc:
                raise RuntimeError(_('Route provider returned invalid data. Try again later.')) from exc
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            retry = exc.headers.get('Retry-After', '180') if exc.headers else '180'
            raise RateLimitError(_('Route request limit (HTTP 429).'),
                                 retry_after=int(retry) if str(retry).isdigit() else 180) from exc
        raise RuntimeError(_('Route lookup unavailable (HTTP {value0}).').format(value0=exc.code)) from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError(_('Could not retrieve origin and destination.')) from exc
    # Log whether the server returned a JSON string, list or object; never
    # misreport an empty association as a successful route lookup.
    route = parse_routeset(payload, callsign, {**AIRPORTS, **{entry[0]: entry for entry in AIRPORTS.values()}})
    logging.getLogger('aeroscope.routes').info(
        _('routeset callsign=%s format=%s association=%s'),
        callsign, type(payload).__name__, _('found') if route else _('not found'))
    return route


def search_historical_flights(kind: str, term: str, *, days: int = 30,
                              max_pages: int = 5, max_results: int = 12) -> list[dict]:
    """Bounded, on-demand archive search by callsign, registration or ICAO24.

    Never call from autocomplete keystrokes. ADSB.aero allows a 7-day window
    per page; cursors continue into older windows. Exact-match filtered because
    prefix predicates also match other aircraft (ARCANJO9 vs ARCANJO90).
    No trajectory payload is downloaded until the user picks a result.
    """
    import re
    if kind not in ('callsign', 'registration', 'hex'):
        raise ValueError(_('Invalid historical search type.'))
    token = str(term or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9-]{3,12}', token):
        raise ValueError(_('Invalid aircraft identifier.'))
    if kind == 'hex':
        if not re.fullmatch(r'[0-9A-F]{6}', token):
            raise ValueError(_('Invalid ICAO24.'))
        match = {'icao24': [token.lower()]}
    elif kind == 'registration':
        match = {'registration_prefix': token}
    else:
        match = {'callsign_prefix': token}

    days = max(1, min(90, int(days)))
    max_pages = max(1, min(8, int(max_pages)))
    max_results = max(1, min(30, int(max_results)))
    start = datetime.now(timezone.utc) - timedelta(days=days)
    base = {
        'match': match,
        'start_from': start.isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'window_days': 7,
        'limit': 80,
        'include_path': False,
    }
    results = []
    seen = set()
    cursor = None
    logger = logging.getLogger('aeroscope.history')
    logger.info(_('Historical search started: type=%s, query=%s, period=%s days, maximum=%s pages'),
                kind, token, days, max_pages)
    norm_token = token.replace('-', '').replace(' ', '')
    for _page_index in range(max_pages):
        payload = dict(base)
        if cursor:
            payload['cursor'] = cursor
        data = _post_json(f'{AERO_API}/query', payload, timeout=20)
        logger.debug(_('Historical page received for %s: %s raw results'),
                     token, len(data.get('flights') or []) if isinstance(data, dict) else '?')
        if not isinstance(data, dict):
            raise RuntimeError(_('The historical service returned an unexpected format.'))
        for flight in data.get('flights') or []:
            if not isinstance(flight, dict) or not flight.get('flight_id'):
                continue
            value = (str(flight.get('icao24') or '') if kind == 'hex' else
                     str(flight.get('registration') or '') if kind == 'registration' else
                     str(flight.get('callsign') or ''))
            if value.upper().replace('-', '').replace(' ', '') != norm_token:
                continue
            fid = str(flight['flight_id'])
            if fid in seen:
                continue
            seen.add(fid)
            results.append(flight)
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break
        next_cursor = data.get('cursor')
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    results.sort(key=lambda f: str(f.get('start_ts') or ''), reverse=True)
    logger.info(_('Historical search completed: query=%s, exact matches=%s'),
                token, len(results))
    return results[:max_results]


def fetch_history_index(icao24: str) -> list[dict]:
    """Newest archived flights; deliberately bounded to one 7-day page.

    This is archival information, not a promise that the current flight is present.
    """
    if not re.fullmatch(r'[a-fA-F0-9]{6}', icao24):
        raise ValueError(_('Invalid ICAO24 code'))
    response = _post_json(f'{AERO_API}/query', {
        'match': {'icao24': [icao24.lower()]},
        'window_days': 7, 'limit': 8, 'include_path': False,
    })
    flights = response.get('flights', []) if isinstance(response, dict) else []
    return [entry for entry in flights if isinstance(entry, dict) and entry.get('flight_id')][:8]


def fetch_history_replay(flight_id: str):
    """Timed archival flight for playback; no invented time data."""
    if not re.fullmatch(r'[a-fA-F0-9]{6}:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', flight_id):
        raise ValueError(_('Invalid historical identifier'))
    endpoint = urllib.parse.quote(flight_id, safe=':')
    payload = read_json(f'{AERO_API}/flights/{endpoint}', timeout=20, max_bytes=12_000_000)
    replay = parse_historical_replay(payload)
    if replay is None:
        raise ValueError(_('This flight does not have enough positions and timestamps for playback'))
    return replay


def fetch_history_path(flight_id: str) -> list[list[tuple[float, float]]]:
    """Keep every separate MultiLineString run independent; never bridge gaps."""
    if not re.fullmatch(r'[a-fA-F0-9]{6}:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', flight_id):
        raise ValueError(_('Invalid historical identifier'))
    endpoint = urllib.parse.quote(flight_id, safe=':')
    response = read_json(f'{AERO_API}/flights/{endpoint}', timeout=20, max_bytes=12_000_000)
    path = response.get('path') if isinstance(response, dict) else None
    if not isinstance(path, dict) or path.get('type') != 'MultiLineString':
        return []
    segments = []
    for segment in path.get('coordinates', [])[:120]:
        if not isinstance(segment, list):
            continue
        parsed = []
        # Cap rendering density without joining separate coverage runs.
        stride = max(1, len(segment) // 1600)
        for sample in segment[::stride]:
            if not isinstance(sample, (list, tuple)) or len(sample) < 2:
                continue
            lon, lat = _number(sample[0]), _number(sample[1])
            if lon is not None and lat is not None and -180 <= lon <= 180 and -85 <= lat <= 85:
                parsed.append((lat, lon))
        if len(parsed) >= 2:
            segments.append(parsed)
    return segments


def _parse_planespotters_response(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        PHOTO_LOG.warning('API retornou JSON sem objeto na raiz (%s)', type(payload).__name__)
        return None
    photos = payload.get('photos', [])
    if not isinstance(photos, list):
        PHOTO_LOG.warning(_('The photos field is not a list (type: %s)'), type(photos).__name__)
        return None
    PHOTO_LOG.debug('API retornou %s entradas de fotografia; campos raiz: %s',
                    len(photos), ','.join(payload.keys()))
    if not photos:
        return None
    rejected = 0
    for photo in photos[:5]:
        if not isinstance(photo, dict):
            continue
        for field in ('thumbnail_large', 'thumbnail'):
            thumbnail = photo.get(field) or {}
            image_url = thumbnail.get('src') if isinstance(thumbnail, dict) else None
            normalized = _photo_url(image_url)
            if not normalized:
                if image_url:
                    rejected += 1
                    parsed = urllib.parse.urlsplit(str(image_url))
                    PHOTO_LOG.debug(_('Skipping unauthorized/invalid thumbnail URL: field=%s host=%s'),
                                    field, parsed.hostname)
                continue
            page_url = _photo_url(photo.get('link'), page=True) or 'https://www.planespotters.net/'
            PHOTO_LOG.info(_('Thumbnail found (field=%s, host=%s), photographer=%s'),
                           field, urllib.parse.urlsplit(normalized).hostname,
                           str(photo.get('photographer') or _('not specified'))[:80])
            return {'src': normalized, 'link': page_url,
                    'photographer': str(photo.get('photographer') or _('Unknown author'))[:120]}
    PHOTO_LOG.warning(_('JSON contains %s photos but no valid thumbnail (rejected URLs=%s)'),
                      len(photos), rejected)
    return None


def _photo_json_get(url: str, identifier: str, timeout: int = 12) -> dict:
    """GET metadata with explicit HTTP status and useful error messages."""
    req = urllib.request.Request(url, headers={
        'User-Agent': AGENT,
        'Accept': 'application/json',
    })
    PHOTO_LOG.info(_('Checking Planespotters for %s'), identifier)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            kind = response.headers.get('Content-Type', '')
            body = response.read(500_001)
            PHOTO_LOG.info('Consulta %s: HTTP %s, content-type=%s, bytes=%s',
                           identifier, status, kind, len(body))
            if len(body) > 500_000:
                raise RuntimeError('Resposta da API de fotos excede 500 KB')
            try:
                return json.loads(body.decode('utf-8'))
            except (ValueError, UnicodeError) as exc:
                PHOTO_LOG.warning(_('Planespotters response is not valid JSON (%s)'), identifier)
                raise RuntimeError(_('The photo API returned invalid data')) from exc
    except urllib.error.HTTPError as exc:
        PHOTO_LOG.warning('Consulta %s: HTTP %s %s', identifier, exc.code, exc.reason)
        if exc.code == 429:
            retry = exc.headers.get('Retry-After', '120') if exc.headers else '120'
            raise RateLimitError(_('Planespotters: HTTP 429 request limit'),
                                 retry_after=int(retry) if str(retry).isdigit() else 120) from exc
        raise RuntimeError(f'Planespotters recusou a consulta: HTTP {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        PHOTO_LOG.warning(_('Network failure at %s: %s'), identifier, exc)
        raise RuntimeError(_('Could not connect to Planespotters: {value0}').format(value0=getattr(exc, 'reason', str(exc)))) from exc


def fetch_photo_details(icao24: str, registration: str = '') -> dict | None:
    """Query ICAO24, then registration; log each result without hiding errors."""
    if not re.fullmatch(r'[a-fA-F0-9]{6}', icao24):
        raise ValueError(_('Invalid ICAO24 code'))
    endpoints = [(f'{PHOTO_API}/hex/{icao24.lower()}', 'ICAO24 ' + icao24.lower())]
    reg = (registration or '').strip().upper()
    if re.fullmatch(r'[A-Z0-9-]{3,12}', reg):
        endpoints.append((f'{PHOTO_API}/reg/{urllib.parse.quote(reg)}', _('registration ') + reg))
    PHOTO_LOG.info(_('Starting photo search: ICAO24=%s registration=%s'),
                   icao24.lower(), reg or _('(not specified)'))
    failures = []
    ok = 0
    for endpoint, identifier in endpoints:
        try:
            result = _photo_json_get(endpoint, identifier)
            ok += 1
            image = _parse_planespotters_response(result)
            if image:
                PHOTO_LOG.info(_('Photo available for %s; downloading thumbnail'), identifier)
                return image
            PHOTO_LOG.info(_('No compatible thumbnail for %s'), identifier)
        except RateLimitError:
            PHOTO_LOG.warning(_('Planespotters rate limit reached; stopping further photo requests'))
            raise
        except (RuntimeError, ValueError) as exc:
            PHOTO_LOG.warning(_('Error fetching %s: %s'), identifier, exc)
            failures.append(f'{identifier}: {exc}')
    if failures:
        # Do not announce "no photograph" when one lookup was blocked.
        raise RuntimeError(_('Incomplete photo lookup: ') + '; '.join(failures)[:240])
    PHOTO_LOG.info(_('No photos found on Planespotters for %s / %s (%s requests)'),
                   icao24.lower(), reg or '-', ok)
    return None


def download_thumbnail(url: str) -> bytes:
    """Download a permitted thumbnail into RAM for display, no disk cache."""
    normalized = _photo_url(url)
    if not normalized:
        raise ValueError(_('Unauthorized photo domain'))
    host = urllib.parse.urlsplit(normalized).hostname
    PHOTO_LOG.info(_('Downloading thumbnail from host %s'), host)
    req = urllib.request.Request(normalized, headers={
        'User-Agent': AGENT,
        'Accept': 'image/avif,image/webp,image/jpeg,image/png,image/*;q=0.8',
        'Referer': 'https://www.planespotters.net/',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            final_url = response.geturl()
            if not _photo_url(final_url):
                raise ValueError(_('Photo redirect to unauthorized domain'))
            status = response.getcode()
            kind = response.headers.get('Content-Type', '').split(';')[0].lower().strip()
            content = response.read(1_500_001)
            PHOTO_LOG.info(_('Thumbnail: HTTP %s, content-type=%s, %s bytes, source=%s'),
                           status, kind, len(content), urllib.parse.urlsplit(final_url).hostname)
            if kind not in ('image/jpeg', 'image/png', 'image/webp', 'image/avif', 'image/gif'):
                raise RuntimeError(_('Thumbnail content is not an image (Content-Type: {value0})').format(value0=kind or 'ausente'))
            if len(content) > 1_500_000:
                raise RuntimeError(_('Thumbnail exceeds the 1.5 MB limit'))
            if not content:
                raise RuntimeError('Servidor retornou imagem vazia')
            return content
    except urllib.error.HTTPError as exc:
        PHOTO_LOG.warning(_('Thumbnail download failed: HTTP %s'), exc.code)
        raise RuntimeError(_('Thumbnail download refused: HTTP {value0}').format(value0=exc.code)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        PHOTO_LOG.warning(_('Network error downloading thumbnail: %s'), exc)
        raise RuntimeError(_('Network error downloading thumbnail: {value0}').format(value0=getattr(exc, 'reason', str(exc)))) from exc


def fetch_areas(queries):
    """Fetch and merge a small, bounded set of ADSB.lol region queries.

    Request concurrency is capped at 2. A partially failing tile is allowed,
    but a totally failed coverage reports the error rather than an empty radar.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    queries = list(queries)[:6]
    if not queries:
        return []
    combined = {}
    failures = []
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='adsb-tiles') as pool:
        futures = [pool.submit(fetch_area, lat, lon, radius) for lat, lon, radius in queries]
        for future in as_completed(futures):
            try:
                for plane in future.result():
                    if plane.hex not in combined or plane.seen < combined[plane.hex].seen:
                        combined[plane.hex] = plane
            except Exception as exc:
                failures.append(str(exc))
    if len(failures) == len(queries):
        raise RuntimeError(failures[0])
    return list(combined.values())


def fetch_airport_movements(icao, iata, lat, lon):
    """Historical start/end positions, not airport schedules or live arrivals.

    ADSB.aero does NOT have an airport-code predicate. Prefer airport-provided
    airspace polygons; fall back to a modest 5-km circle when none are present.
    """
    if not re.fullmatch(r'[A-Z0-9]{3,4}', icao):
        raise ValueError(_('Invalid airport ICAO'))
    location = read_json(f'{AERO_API}/airports/{urllib.parse.quote(icao)}')
    airspaces = location.get('airspaces') if isinstance(location, dict) else None
    geom = next((a['geometry'] for a in airspaces if isinstance(a, dict)
                 and isinstance(a.get('geometry'), dict)), None) if isinstance(airspaces, list) else None
    if not geom:
        geom = {'type': 'Circle', 'coordinates': [lon, lat], 'radius': 5000}
    results = {}
    for key, mode in (('partidas', 'start'), ('chegadas', 'end')):
        response = _post_json(f'{AERO_API}/query', {
            'match': {'endpoint_within': {'mode': mode, 'geometry': geom}},
            'window_days': 7, 'limit': 8, 'include_path': False,
        })
        flights = response.get('flights', []) if isinstance(response, dict) else []
        results[key] = [f for f in flights if isinstance(f, dict)][:8]
    return results
