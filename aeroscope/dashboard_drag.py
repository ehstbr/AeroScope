"""Stable movement for GTK4 overlays that move under the pointer.

GtkGestureDrag's offsets are in the *moving widget's* coordinates, while raw
GdkEvent positions are expressed in the GdkSurface's fixed coordinates.
"""
from __future__ import annotations

import math


def surface_point(gesture):
    """Return (x,y) in stable surface coordinates, or None if unavailable.

    PyGObject's Gdk.Event.get_position() returns (ok, x, y); lightweight
    bindings/mocks may expose (x, y) instead.
    """
    event = gesture.get_last_event(None)
    if event is None:
        return None
    result = event.get_position()
    if result is None:
        return None
    if len(result) == 3:
        ok, x, y = result
        if not ok:
            return None
    elif len(result) == 2:
        x, y = result
    else:
        return None
    try:
        x, y = float(x), float(y)
        return (x, y) if math.isfinite(x) and math.isfinite(y) else None
    except (ValueError, TypeError):
        return None


def dragged_position(origin, pointer):
    """(start margin x/y, start surface x/y) + current *surface* delta."""
    return (origin[0] + pointer[0] - origin[2],
            origin[1] + pointer[1] - origin[3])
