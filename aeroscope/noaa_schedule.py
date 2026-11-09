"""Policy for when to refresh NOAA overlays, independent of GTK and HTTP.

METAR and SIGMET overlays are spatial samples, not a stream of positions.
A small map pan inside the 7 x 6 degree NOAA bbox can reuse cached data.
"""
from __future__ import annotations

from .geoview import distance_nm

REGION_CHANGE_NM = 75.0
MIN_REGION_GAP_SECONDS = 15.0


def weather_refresh_decision(now: float, due_at: float, current_center,
                             queried_center, requested_at: float):
    """Return (refresh, wait_seconds), where wait is for a new region only.

    The periodic refresh is due when *now* reaches the completion-based
    deadline. A meaningful center move can refresh early, but rapid panning
    cannot send more than one regional request per minimum interval.
    """
    if queried_center is None:
        return True, 0.0  # initial map snapshot
    moved = distance_nm(*current_center, *queried_center) >= REGION_CHANGE_NM
    if not moved:
        return now >= due_at, 0.0
    remaining = max(0.0, MIN_REGION_GAP_SECONDS - (now - requested_at))
    if remaining > 0:
        return False, remaining
    return True, 0.0
