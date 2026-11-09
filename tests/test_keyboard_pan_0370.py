"""Pan easing is tested without GTK so builds work on any Linux host."""
import ast
import math
from pathlib import Path

from aeroscope.keyboard_pan import KeyboardPan, KEY_DIRECTIONS

ROOT = Path(__file__).resolve().parents[1]


def advance(pan, start, seconds, fps=60):
    total_x = total_y = 0.0
    count = round(seconds * fps)
    for i in range(1, count + 1):
        dx, dy, _ = pan.step(start + i / fps)
        total_x += dx
        total_y += dy
    return total_x, total_y


def test_short_tap_has_smooth_momentum_and_stops():
    p = KeyboardPan()
    assert p.press('Right', 0)
    x1, y1 = advance(p, 0, .08)
    assert 15 < x1 < 60 and y1 == 0
    assert p.release('Right')
    x2, _ = advance(p, .08, .7)
    assert 10 < x2 < 100
    assert p.last_time is None
    assert p.vx == 0 and not p.held


def test_hold_accelerates_and_repeat_does_not_restart_animation():
    p = KeyboardPan()
    assert p.press('Up', 0)
    x0, y0 = advance(p, 0, .1)
    speed1 = p.vy
    assert p.press('Up', .1)
    x1, y1 = advance(p, .1, .4)
    assert x0 == x1 == 0
    assert y0 < 0 and y1 < y0
    assert p.vy < speed1  # velocity magnitude increased
    assert len(p.held) == 1


def test_diagonal_speed_is_normalized():
    p = KeyboardPan()
    p.press('Right', 0)
    p.press('Down', 0)
    x, y = advance(p, 0, 1)
    # A pre-existing horizontal velocity eases toward the diagonal.
    assert abs(x-y) < 60
    assert abs(p.vx-p.vy) < 2
    assert math.hypot(p.vx, p.vy) <= p.SPEED + 1
    assert 'Left' in KEY_DIRECTIONS and 'KP_Down' in KEY_DIRECTIONS


def test_opposing_keys_cancel_and_release_recovers_direction():
    p = KeyboardPan()
    p.press('Left', 0)
    advance(p, 0, .5)
    p.press('Right', .5)
    advance(p, .5, .8)
    assert abs(p.vx) < 5
    p.release('Left')
    advance(p, .8, 1)
    assert p.vx > 400


def test_stop_and_framerate_independence():
    p1 = KeyboardPan()
    p2 = KeyboardPan()
    p1.press('Left', 0)
    p2.press('Left', 0)
    x1, _ = advance(p1, 0, .6, 60)
    x2, _ = advance(p2, 0, .6, 30)
    assert abs(x1-x2) < 2
    p1.reset()
    assert p1.last_time is None
    assert p1.held == set()
    assert not p1.press('Unknown', 0)


def test_gnome_integration_preserves_text_focus_and_map_refresh_debounce():
    source = (ROOT / 'aeroscope/ui.py').read_text()
    ast.parse(source)
    assert 'self.get_focus() is not self.map' in source
    assert "shortcut_keys.connect('key-released', self._keyboard_pan_released)" in source
    assert 'GLib.timeout_add(16, self._keyboard_pan_tick)' in source
    assert 'self.viewport.widget_coords_to_location(' in source
    assert 'self.map.center_on(lat, lon)' in source
    assert 'self._stop_keyboard_pan()' in source
    assert 'GLib.timeout_add(850, self._view_settled)' in source
