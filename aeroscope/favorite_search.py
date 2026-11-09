"""Local favorite-search candidates: aircraft, known airports and NOAA METAR stations.

No API calls on keystrokes. A station outside the local weather cache can be
resolved only by an explicit four-character ICAO lookup on the NOAA API.
"""
from __future__ import annotations

from dataclasses import dataclass
from .search_suggestions import normalized, relevance


@dataclass(frozen=True)
class FavoriteCandidate:
    kind: str  # aircraft, airport, station
    key: str  # aircraft registration/icao24, airport IATA, station ICAO
    title: str
    subtitle: str
    lat: float | None = None
    lon: float | None = None
    aircraft_kind: str = ''


def favorite_candidates(query, aircraft, airports, stations, *, per_kind=6):
    """Rank locally available favorites; one station/aircraft appears once.

    Airport ICAOs match the associated IATA favorite so an ICAO search does
    not create a duplicate weather-station favorite for a fixed airport.
    """
    if not normalized(query):
        return []
    planes, airfields, weather = [], [], []
    icao_airports = {info[0] for info in airports.values()}
    seen_planes, seen_stations = set(), set()
    for plane in aircraft or ():
        reg = str(getattr(plane, 'registration', '') or '').strip().upper()
        hexcode = str(getattr(plane, 'hex', '') or '').strip().upper()
        flight = str(getattr(plane, 'flight', '') or '').strip().upper()
        model = str(getattr(plane, 'model', '') or '').strip()
        rank = relevance(query, reg, hexcode, flight, model)
        key = reg or hexcode
        if rank is None or not key or key in seen_planes:
            continue
        seen_planes.add(key)
        planes.append((rank, normalized(flight or reg or hexcode), FavoriteCandidate(
            'aircraft', key, flight or reg or hexcode,
            ' · '.join(part for part in (reg or hexcode, model) if part),
            getattr(plane, 'lat', None), getattr(plane, 'lon', None),
            'registration' if reg else 'icao')))
    for iata, details in (airports or {}).items():
        icao, name, lat, lon = details
        rank = relevance(query, iata, icao, name)
        if rank is not None:
            airfields.append((rank, normalized(iata), FavoriteCandidate(
                'airport', iata, f'{iata} · {name}', icao, lat, lon)))
    for station in stations or ():
        code = str(getattr(station, 'station', '') or '').strip().upper()
        if not code or code in icao_airports or code in seen_stations:
            continue
        rank = relevance(query, code)
        if rank is None:
            continue
        seen_stations.add(code)
        weather.append((rank, normalized(code), FavoriteCandidate(
            'station', code, code, 'NOAA METAR',
            getattr(station, 'lat', None), getattr(station, 'lon', None))))
    return [candidate for group in (planes, airfields, weather)
            for _, _, candidate in sorted(group)[:per_kind]]
