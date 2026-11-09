"""0.3.57: the GTK-interaction regressions found on a real touchscreen."""
from pathlib import Path

from aeroscope.dashboard_drag import surface_point, dragged_position
from aeroscope.context_tooltips import protect_context_menu


class Event:
    def __init__(self, point):
        self.point = point

    def get_position(self):
        return self.point


class Gesture:
    def __init__(self, point):
        self.point = point

    def get_last_event(self, sequence):
        assert sequence is None
        return Event(self.point)


def test_drag_uses_stable_surface_coordinates_not_widget_local_delta():
    # Drag starts at surface (300,120) with a card at (50,40).
    start = (50, 40, *surface_point(Gesture((True, 300, 120))))
    assert dragged_position(start, surface_point(Gesture((True, 340, 150)))) == (90, 70)
    # Widget moved beneath cursor: its *local* drag offset jumps, but absolute
    # surface event (360,155) still yields a continuous (110,75) position.
    assert dragged_position(start, surface_point(Gesture((True, 360, 155)))) == (110, 75)
    assert dragged_position(start, surface_point(Gesture((True, 360, 155)))) == (110, 75)


def test_surface_coordinates_pygobject_and_invalid_events():
    assert surface_point(Gesture((True, 3.5, 9))) == (3.5, 9)
    assert surface_point(Gesture((3.5, 9))) == (3.5, 9)
    assert surface_point(Gesture((False, 3, 9))) is None
    assert surface_point(Gesture((True, float('nan'), 9))) is None
    assert surface_point(Gesture(None)) is None


class FakeMarker:
    def __init__(self, text, present=True):
        self.tip = text
        self.parent = object() if present else None

    def get_tooltip_text(self):
        return self.tip

    def set_tooltip_text(self, tip):
        self.tip = tip

    def get_parent(self):
        return self.parent


class FakePopover:
    def __init__(self):
        self.handlers = {}

    def connect(self, signal, handler):
        self.handlers[signal] = handler

    def close(self):
        self.handlers['closed'](self)


def test_right_click_suspends_tooltip_until_menu_closed():
    marker, menu = FakeMarker('SBPA  IFR'), FakePopover()
    deferred, detached = [], []
    protect_context_menu(menu, marker, deferred.append, detached.append)
    assert marker.tip is None  # Old tooltip cannot compete with the popover.
    menu.close()
    assert marker.tip is None  # Cleanup is intentionally deferred past event.
    deferred.pop()()
    assert marker.tip == 'SBPA  IFR'
    assert detached == [menu]


def test_closed_popup_with_removed_marker_does_not_restore_tooltip():
    marker, menu = FakeMarker('SBPA', present=False), FakePopover()
    queue, detached = [], []
    protect_context_menu(menu, marker, queue.append, detached.append)
    menu.close()
    queue.pop()()
    assert marker.tip is None
    assert detached == [menu]


def test_compact_card_hides_both_timestamps_keeps_status_visible():
    widget = Path(__file__).resolve().parents[1] / 'aeroscope/floating_widget.py'
    code = widget.read_text()
    assert "self.compact_category.set_visible(self.collapsed)" in code
    assert "self.expanded_content.append(self.observed)" in code
    assert "self.expanded_content.append(self.checked)" in code
    assert "self.title_label.set_label(self.code if self.collapsed" in code
    assert 'surface_point(gesture)' in code


def test_minimap_mirrors_main_tower_and_stations_without_independent_timer():
    root = Path(__file__).resolve().parents[1]
    mini = (root / 'aeroscope/mini_map.py').read_text()
    ui = (root / 'aeroscope/ui.py').read_text()
    weather = (root / 'aeroscope/weather_ui.py').read_text()
    assert 'RadarWindow._draw_radar(self, area, cr, width, height)' in mini
    assert 'RadarWindow._draw_relative_clock(self, cr, width, height)' in mini
    assert 'return self.radar._tower_sweep_angle(now)' in mini
    assert 'pip.redraw_tower_sweep()' in ui
    assert 'pip.sync_visuals()' in ui
    assert 'self.sync_airports()' in mini
    assert 'if metar.station in fixed_stations and enabled_airports:' in weather
