"""Opt-in aircraft watchlist and worldwide emergency-transponder lookup.

The live regional radar is intentionally separate: these queries use the
ADSB.lol global registration/ICAO/squawk filters, never a world grid scan.
"""
from __future__ import annotations
from .i18n import _

import json
import logging
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path

from .data import API, read_json, parse_aircraft, RateLimitError
from .settings import CONFIG_DIR

LOG = logging.getLogger('aeroscope.monitor')
FAVORITES_FILE = CONFIG_DIR / 'favorites.json'
MAX_FAVORITES = 12
ALERT_CODES = {'7700': _('General emergency'), '7600': _('Radio failure'), '7500': _('Unlawful interference')}


@dataclass(frozen=True)
class Favorite:
    kind: str  # 'registration' or 'icao'
    value: str
    label: str = ''

    @property
    def key(self) -> str:
        return f'{self.kind}:{self.value}'


def normalize_favorite(kind: str, value: str, label: str = '') -> Favorite:
    kind = str(kind).lower().strip()
    code = str(value).upper().strip().replace(' ', '')
    if kind == 'icao':
        if not re.fullmatch(r'[0-9A-F]{6}', code):
            raise ValueError(_('The ICAO24 address must contain six hexadecimal digits.'))
    elif kind == 'registration':
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9\-]{1,11}', code):
            raise ValueError(_('Invalid registration (e.g. PT-MUJ, PR-ABC).'))
    else:
        raise ValueError(_('Invalid identifier type.'))
    return Favorite(kind, code, str(label or '').strip()[:70])


def load_favorites(path: Path = FAVORITES_FILE) -> list[Favorite]:
    try:
        parsed = json.loads(path.read_text('utf-8'))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    found = []
    keys = set()
    for item in parsed[:100]:
        try:
            if not isinstance(item, dict):
                continue
            fav = normalize_favorite(item.get('kind', ''), item.get('value', ''), item.get('label', ''))
            if fav.key not in keys:
                found.append(fav)
                keys.add(fav.key)
            if len(found) == MAX_FAVORITES:
                break
        except ValueError:
            continue
    return found


def save_favorites(favorites: list[Favorite], path: Path = FAVORITES_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps([asdict(f) for f in favorites[:MAX_FAVORITES]],
                               ensure_ascii=False, indent=2) + '\n', 'utf-8')
    temp.replace(path)


def add_favorite(favorites: list[Favorite], kind: str, value: str, label: str = '') -> list[Favorite]:
    fav = normalize_favorite(kind, value, label)
    if any(x.key == fav.key for x in favorites):
        return list(favorites)
    if len(favorites) >= MAX_FAVORITES:
        raise ValueError(_('The monitor supports up to {value0} aircraft, to protect the public API.').format(value0=MAX_FAVORITES))
    return [*favorites, fav]


def is_favorite(favorites: list[Favorite], registration: str = '', icao: str = '') -> bool:
    """Match by either registration or ICAO24, regardless of favorite type."""
    reg = (registration or '').strip().upper()
    code = (icao or '').strip().upper()
    return any((f.kind == 'registration' and reg and f.value == reg)
               or (f.kind == 'icao' and code and f.value == code)
               for f in favorites)



def live_favorite_checks(favorites: list[Favorite], aircraft, checked_at: float | None = None,
                         max_age: float = 90) -> dict:
    """Reuse fresh radar positions for saved favorites without a network call.

    Missing planes are *not* marked offline: a regional radar cannot establish
    that an aircraft stopped transmitting somewhere else in the world.
    The stored result uses the same tuple as the independent global monitor.
    """
    if checked_at is None:
        checked_at = time.time()
    by_reg = {}
    by_hex = {}
    for plane in aircraft:
        try:
            age = float(plane.seen)
        except (AttributeError, TypeError, ValueError):
            continue
        if not 0 <= age <= max_age:
            continue
        reg = str(getattr(plane, 'registration', '') or '').strip().upper()
        hexid = str(getattr(plane, 'hex', '') or '').strip().upper()
        if reg and (reg not in by_reg or age < by_reg[reg].seen):
            by_reg[reg] = plane
        if hexid and (hexid not in by_hex or age < by_hex[hexid].seen):
            by_hex[hexid] = plane
    checks = {}
    for fav in favorites:
        plane = (by_reg if fav.kind == 'registration' else by_hex).get(fav.value)
        if plane is not None:
            checks[fav.key] = ('active', plane, checked_at,
                               str(getattr(plane, 'flight', '') or '').strip())
    return checks


def fetch_favorite(fav: Favorite):
    """Return (state, Aircraft|None, callsign).

    A recent ADS-B message without GPS position is *detected without position*,
    not offline. No match means *not recently seen by this network*, not on ground.
    Errors must be propagated rather than converted to offline states.
    """
    endpoint = 'icao' if fav.kind == 'icao' else 'reg'
    url = f'{API}/{endpoint}/{urllib.parse.quote(fav.value, safe="")}'
    payload = read_json(url, timeout=11)
    matches = []
    for row in payload.get('ac', []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict):
            continue
        identifier = str(row.get('hex') if fav.kind == 'icao' else row.get('r') or '').upper().strip()
        if identifier != fav.value:
            continue
        try:
            seen = float(row.get('seen'))
        except (TypeError, ValueError):
            continue
        if not 0 <= seen <= 90:
            continue
        matches.append((seen, row))
    if not matches:
        return ('offline', None, '')
    row = min(matches, key=lambda item: item[0])[1]
    aircraft = parse_aircraft({'ac': [row]})
    return ('active' if aircraft else 'active-no-position',
            aircraft[0] if aircraft else None,
            str(row.get('flight') or '').strip())


def fetch_global_emergencies():
    """Three network-wide calls, never geographical tiling.

    Keep rows without GPS position in the list; clicking 'map' is only offered
    when coordinates exist and are recent. Failures per code remain explicit.
    A 429 stops all remaining calls immediately; caller must implement backoff.
    """
    results = []
    errors = {}
    known = set()
    for code, label in ALERT_CODES.items():
        try:
            payload = read_json(f'{API}/squawk/{code}', timeout=12)
        except RateLimitError:
            raise
        except (RuntimeError, ValueError, OSError) as exc:
            LOG.warning('Consulta global %s falhou: %s', code, exc)
            errors[code] = str(exc)
            continue
        if not isinstance(payload, dict):
            errors[code] = _('Invalid response.')
            continue
        for row in payload.get('ac', []):
            if not isinstance(row, dict):
                continue
            if str(row.get('squawk') or '').strip() != code:
                # API call is by squawk. Never mix an incompatible status.
                continue
            try:
                if not 0 <= float(row.get('seen')) <= 90:
                    continue
            except (TypeError, ValueError):
                continue
            hexid = str(row.get('hex') or '').strip().lower()
            if not hexid or hexid in known:
                continue
            known.add(hexid)
            position = None
            planes = parse_aircraft({'ac': [row]})
            if planes:
                position = planes[0]
            results.append({
                'hex': hexid,
                'flight': str(row.get('flight') or '').strip(),
                'registration': str(row.get('r') or '').strip(),
                'model': str(row.get('t') or '').strip(),
                'squawk': code,
                'description': label,
                'aircraft': position,
            })
    priority = {'7700': 0, '7600': 1, '7500': 2}
    results.sort(key=lambda x: (priority[x['squawk']], x['flight'] or x['registration'] or x['hex']))
    return results, errors, time.time()
