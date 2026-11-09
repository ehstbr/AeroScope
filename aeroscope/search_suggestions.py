"""Grouped, accent-insensitive suggestions for the native GNOME search popover.

Local results require no network calls. Geocoding results are supplied by the
existing Open-Meteo client separately and are never requested from this module.
"""
from __future__ import annotations
from .i18n import _

from dataclasses import dataclass
import unicodedata
import re
from datetime import datetime, timezone


@dataclass(frozen=True)
class SearchSuggestion:
    kind: str  # aircraft, airport, city, history, archive_action
    key: str
    title: str
    subtitle: str
    lat: float | None = None
    lon: float | None = None



def classify_aircraft_identifier(query: str) -> str | None:
    """Recognize global aircraft searches, including long callsigns ARCANJO9.

    Do not classify arbitrary place names as callsigns. Other, ambiguous
    identifiers can be submitted explicitly through the history search action.
    """
    term = str(query or '').strip().upper().replace(' ', '')
    if re.fullmatch(r'[0-9A-F]{6}', term):
        return 'hex'
    if re.fullmatch(r'[A-Z]{1,3}-[A-Z0-9]{2,8}', term):
        return 'registration'
    if re.fullmatch(r'[A-Z]{2,10}[0-9][A-Z0-9]{0,5}', term) and len(term) <= 12:
        return 'callsign'
    return None


def historical_suggestions(query: str, entries, limit: int = 12) -> list[SearchSuggestion]:
    """Results come from an explicit ADSB.aero search, never from each keypress."""
    found = []
    for entry in entries or []:
        if not isinstance(entry, dict) or not entry.get('flight_id'):
            continue
        callsign = str(entry.get('callsign') or '').strip()
        registration = str(entry.get('registration') or '').strip()
        hexid = str(entry.get('icao24') or '').strip()
        if relevance(query, callsign, registration, hexid) is None:
            continue
        when = str(entry.get('start_ts') or '')[:16].replace('T', ' ')
        ends = str(entry.get('end_ts') or '')[:16].replace('T', ' ')
        departure = str(entry.get('start_airport_ident') or '?')
        arrival = str(entry.get('end_airport_ident') or '?')
        title = f'{callsign or registration or hexid.upper()} · {when} UTC' if when else (callsign or registration or hexid.upper())
        subtitle = f'{registration or hexid.upper()} · {departure} → {arrival}'
        found.append(SearchSuggestion('history', str(entry['flight_id']), title, subtitle))
        if len(found) >= limit:
            break
    return found

def normalized(value: object) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').casefold())
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return ' '.join(text.split())


def relevance(query: str, *values: object) -> int | None:
    """Stable ranking: exact code/name, prefix, then token or substring."""
    q = normalized(query)
    if not q:
        return None
    score = None
    for value in values:
        candidate = normalized(value)
        if not candidate:
            continue
        # Hyphens may be omitted from registrations and flight numbers.
        cq, cc = q.replace('-', '').replace(' ', ''), candidate.replace('-', '').replace(' ', '')
        if q == candidate or cq == cc:
            rank = 0
        elif candidate.startswith(q) or cc.startswith(cq):
            rank = 1
        elif any(token.startswith(q) for token in candidate.split()):
            rank = 2
        elif q in candidate or cq in cc:
            rank = 3
        else:
            continue
        score = rank if score is None else min(rank, score)
    return score


def local_suggestions(query: str, aircraft, airports, aircraft_label=None,
                      max_aircraft=6, max_airports=6) -> list[SearchSuggestion]:
    """Find airplanes from currently loaded radar data and local airports."""
    if not normalized(query):
        return []
    if aircraft_label is None:
        aircraft_label = lambda code: code or _('Unknown model')

    planes = []
    for plane in aircraft:
        model_label = aircraft_label(getattr(plane, 'model', ''))
        rank = relevance(query, plane.flight, plane.registration, plane.hex,
                         plane.model, model_label)
        if rank is None:
            continue
        identifier = plane.flight or plane.registration or plane.hex.upper()
        subtitle = f'{model_label} · {plane.registration or plane.hex.upper()}'
        planes.append((rank, normalized(identifier), SearchSuggestion(
            'aircraft', plane.hex, identifier, subtitle,
            plane.lat, plane.lon)))
    planes.sort(key=lambda item: (item[0], item[1]))

    found_airports = []
    for iata, data in airports.items():
        icao, name, lat, lon = data
        rank = relevance(query, iata, icao, name)
        if rank is None:
            continue
        found_airports.append((rank, normalized(name), SearchSuggestion(
            'airport', iata, name, _('{value0} / {value1} · Airport').format(value0=iata, value1=icao), lat, lon)))
    found_airports.sort(key=lambda item: (item[0], item[1]))
    return ([item[2] for item in planes[:max_aircraft]] +
            [item[2] for item in found_airports[:max_airports]])


def city_suggestions(query: str, locations, limit=6) -> list[SearchSuggestion]:
    """Convert Open-Meteo results without inventing city coordinates."""
    found = []
    seen = set()
    for city, state, country, lat, lon in locations:
        if not city:
            continue
        if relevance(query, city, f'{city}, {state}', f'{city}, {state}, {country}') is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if not (-85 < lat < 85 and -180 <= lon <= 180):
            continue
        key = (normalized(city), normalized(state), normalized(country), round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)
        subtitle = ', '.join(part for part in (state, country) if part)
        found.append(SearchSuggestion('city', f'{lat:.5f},{lon:.5f}', city, subtitle, lat, lon))
        if len(found) >= limit:
            break
    return found


def grouped_suggestions(suggestions):
    """Keep a predictable group order for both screen and keyboard navigation."""
    return [(kind, [item for item in suggestions if item.kind == kind])
            for kind in ('aircraft', 'history', 'airport', 'city', 'archive_action')
            if any(item.kind == kind for item in suggestions)]
