"""Pure transition detection for aircraft watchlist and worldwide squawk alerts.

Initial polling is a baseline, not a notification. A loss of ADS-B reception is
not equivalent to landing. The airborne predicate is deliberately conservative
and should be displayed as 'possibly airborne', never as a confirmed takeoff.
"""
from __future__ import annotations

import time


def likely_airborne(aircraft) -> bool:
    """Approximation based on two transmitted parameters; not a flight state."""
    if aircraft is None:
        return False
    altitude = getattr(aircraft, 'altitude_ft', None)
    speed = getattr(aircraft, 'speed_kts', None)
    return (isinstance(altitude, (int, float)) and
            isinstance(speed, (int, float)) and
            altitude > 0 and speed >= 50)


class AlertTransitions:
    def __init__(self):
        self._offline_counts = {}
        self._fav_seen = set()
        self._ground_seen = set()
        self._emergency_known = {}  # code -> set(ICAO24)
        self._recently_announced = {}  # (code, ICAO24) -> monotonic seconds

    def favorites_updated(self, checks):
        """Return favorites that reappeared, plausibly airborne, after 2 misses.

        All error/unknown results are ignored so a temporary outage cannot
        manufacture an off -> on transition. New favorites are baselined.
        """
        hits = []
        for key, (state, plane, *_other) in checks.items():
            if state in ('error', 'unknown'):
                continue
            if state == 'offline':
                self._fav_seen.add(key)
                self._offline_counts[key] = min(2, self._offline_counts.get(key, 0) + 1)
                continue
            armed = (key in self._fav_seen and self._offline_counts.get(key, 0) >= 2)
            ground_before = key in self._ground_seen
            self._fav_seen.add(key)
            self._offline_counts[key] = 0
            if state == 'active' and plane is not None and plane.on_ground is True:
                self._ground_seen.add(key)
            elif state == 'active' and likely_airborne(plane):
                self._ground_seen.discard(key)
                if armed or ground_before:
                    hits.append((key, plane))
        return hits

    def remove_favorite(self, key):
        self._offline_counts.pop(key, None)
        self._fav_seen.discard(key)
        self._ground_seen.discard(key)

    def emergencies_updated(self, rows, errors, now=None):
        """Only notify new ICAO24+code, preserving baseline for failed codes."""
        if now is None:
            now = time.monotonic()
        self._recently_announced = {
            key: ts for key, ts in self._recently_announced.items()
            if now - ts < 1800
        }
        grouped = {'7500': set(), '7600': set(), '7700': set()}
        for item in rows:
            code = item.get('squawk')
            ident = str(item.get('hex', '')).lower()
            if code in grouped and ident:
                grouped[code].add(ident)
        hits = []
        for code, current in grouped.items():
            if code in errors:
                continue
            previous = self._emergency_known.get(code)
            if previous is not None:
                for item in rows:
                    if item.get('squawk') != code:
                        continue
                    key = (code, str(item.get('hex', '')).lower())
                    if key[1] in current - previous and key not in self._recently_announced:
                        self._recently_announced[key] = now
                        hits.append(item)
            self._emergency_known[code] = current
        return hits
