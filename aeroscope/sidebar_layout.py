"""Text-layout rules for the narrow, user-resizable GTK inspector.

These decisions are independent of GTK, so the rules for long meteorological
fields and monitor cards can be regression-tested without a display server.
"""
from __future__ import annotations

# Maximum *natural* width of a wrapping text widget, measured in characters.
# The GTK allocation can still be narrower if the user drags the divider.
SIDEBAR_NATURAL_WIDTH_CHARS = 34
MONITOR_NATURAL_WIDTH_CHARS = 28


def needs_wrap(text: object, requested: bool = False) -> bool:
    """Long text must not make a GTK Paned grow horizontally on its own."""
    return requested or len(str(text)) > 30 or '\n' in str(text)


def detail_needs_stacking(title: object, value: object) -> bool:
    """Keep short facts compact; place long METAR/callsign text below the title."""
    t, v = str(title), str(value)
    return ('\n' in v or len(v) > 43 or len(t) + len(v) > 50)
