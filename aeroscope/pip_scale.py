"""One-unit, compact scale-bar calculations for the detached mini-map."""
from __future__ import annotations
import math
from .tower_radar import meters_per_pixel


def compact_scale(latitude: float, zoom: float, units='kmh', max_pixels=76):
    """Return (label, line width in px) using a readable 1/2/5 scale step."""
    mpp = max(0.01, meters_per_pixel(latitude, zoom))
    factor, suffix = {'kmh': (1000.0, 'km'), 'kt': (1852.0, 'NM'),
                      'mph': (1609.344, 'mi')}.get(units, (1000.0, 'km'))
    max_distance = max_pixels * mpp / factor
    if max_distance <= 0 or not math.isfinite(max_distance):
        return '—', 0.0
    base = 10 ** math.floor(math.log10(max_distance))
    nice = max(k * base for k in (1.0, 2.0, 5.0, 10.0) if k * base <= max_distance * (1+1e-10))
    length_px = nice * factor / mpp
    text = f'{nice:g} {suffix}'
    if nice < .01:
        text = f'{nice:.3f} {suffix}'
    return text, max(1.0, min(float(max_pixels), length_px))
