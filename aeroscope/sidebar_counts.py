"""Display-only counts for the AeroScope sidebar tabs (no network/UI dependencies)."""
from __future__ import annotations

from .monitor_alerts import likely_airborne


def tab_label(name: str, count: int | None) -> str:
    """Use an em dash until the source has actually been checked."""
    return f'{name} ({"—" if count is None else max(0, count)})'


def airborne_favorites_count(favorites, statuses: dict) -> int:
    """Count distinct favorite airframes plausibly flying in the last check.

    'active' merely means tracked by the network; it is not itself evidence
    of flight. Don't count ground reports, missing positions or failed checks.
    Duplicate favorites by ICAO24/registration count as one airframe.
    """
    counted = set()
    for fav in favorites:
        state, plane, *_rest = statuses.get(fav.key, ('unknown', None))
        if (state != 'active' or plane is None
                or getattr(plane, 'on_ground', None) is True
                or not likely_airborne(plane)):
            continue
        identifier = str(getattr(plane, 'hex', '') or '').lower() or fav.key
        counted.add(identifier)
    return len(counted)
