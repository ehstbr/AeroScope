"""Pure geometry for AeroScope's optional control-tower presentation.

The scanning beam is a visual timing gate for positions ALREADY received from
ADSB.lol. It is not a receiver, prediction, or independent network poller.
"""
from __future__ import annotations
import math


def bearing_on_screen(dx: float, dy: float) -> float:
    """Clockwise bearing from map-up, in degrees."""
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def crossed_clockwise(previous: float, current: float, target: float, *, full_turn=False) -> bool:
    """Whether a clockwise rotating beam passed the given bearing."""
    if full_turn:
        return True
    distance = (current - previous) % 360.0
    target_distance = (target - previous) % 360.0
    return 0 <= target_distance <= distance and distance > 0



def crossed_moving_target(previous_beam: float, current_beam: float,
                          previous_target: float, current_target: float,
                          *, full_turn: bool = False) -> bool:
    """Did a clockwise radar beam intersect the *moving* virtual target?

    Target angles are the viewport bearings of the point interpolated from
    the last two received ADS-B fixes at consecutive animation frames. The
    visible (held) marker is intentionally never used for this test.

    Work in relative bearings and unwrap only one frame: this recognizes a
    crossing even while the projected target drifts clockwise or anticlockwise.
    It also handles the 359 -> 0 degree boundary without a false full sweep.
    """
    if full_turn:
        return True
    beam_step = (float(current_beam) - float(previous_beam)) % 360.0
    if not 0 < beam_step <= 90:  # discontinuity after suspend/reset
        return False
    target_step = ((float(current_target) - float(previous_target) + 180) % 360) - 180
    if abs(target_step) >= 90:  # camera teleported; wait for a stable frame
        return False
    relative_before = ((float(previous_target) - float(previous_beam) + 180) % 360) - 180
    relative_after = relative_before + target_step - beam_step
    return (relative_before >= 0 >= relative_after or
            relative_before <= 0 <= relative_after)


def ring_label(distance_nm: float, velocity_unit: str) -> str:
    """Share the application's main measurement-system choice."""
    factors = {'kt': (1.0, 'NM'), 'mph': (1.15077945, 'mi'),
               'kmh': (1.852, 'km')}
    factor, unit = factors.get(velocity_unit, factors['kmh'])
    value = max(0.0, distance_nm * factor)
    if value < 10:
        number = f'{value:.1f}'
    else:
        number = f'{round(value):.0f}'
    return f'{number} {unit}'


def meters_per_pixel(latitude: float, zoom: float) -> float:
    """Fallback Web Mercator resolution where widget conversion is absent."""
    return (40075016.686 / (256 * 2 ** zoom)) * max(0.01, math.cos(math.radians(latitude)))


def full_map_radius(width: float, height: float, cx: float | None = None,
                    cy: float | None = None) -> float:
    """Radius of a sweep that covers even the corners of a rectangular map."""
    x = width/2 if cx is None else cx
    y = height/2 if cy is None else cy
    return math.hypot(max(x, width-x), max(y, height-y))


def clock_hour_bearings(aircraft_heading: float) -> tuple[float, ...]:
    """Hour 0/12 follows aircraft's actual nose; 2h means +60 degrees."""
    heading = float(aircraft_heading) % 360
    return tuple((heading + n*30) % 360 for n in range(12))


def clock_ring_radius(width: float, height: float, cx: float, cy: float) -> float:
    """Fixed screen-space aircraft clock, independent of aircraft/map position.

    The selected aircraft is the center. When close to a viewport edge, the
    clock is naturally clipped (never squeezed or recentered). Only resizing a
    very narrow application window can reduce the nominal 168 px radius.
    """
    return max(0.0, min(168.0, 0.40 * min(width, height)))


def ring_label_anchor(cx: float, cy: float, radius: float,
                      width: float, height: float, label_width: float) -> tuple[float, float]:
    """Choose a visible intersection of a map-wide ring, preferring NE."""
    candidates = []
    # For outer rings a fixed 51-degree anchor is often outside the map.
    for angle in range(0, 360, 2):
        rad = math.radians(angle)
        x = cx + math.sin(rad)*radius
        y = cy - math.cos(rad)*radius
        left = x - label_width/2
        top = y - 11
        if 4 <= left <= width-label_width-4 and 4 <= top <= height-22:
            delta = abs(((angle - 51 + 180) % 360) - 180)
            candidates.append((delta, left, top))
    if candidates:
        _, x, y = min(candidates)
        return x, y
    # A circle can touch only the screen corners (or be fully off-screen).
    # In that case a clamped label would be *detached from its circle*.
    # Prefer no label over a misleading distance indicator.
    return None
