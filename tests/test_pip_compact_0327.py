"""Small-window and marker gestures: pure tests and source-level contract.

GUI runtime still needs validation in a real GNOME/KDE session.
"""
from pathlib import Path
from unittest import mock

from aeroscope.pip_scale import compact_scale
from aeroscope.pip_windowing import (_XEvent, request_window_above,
                                       request_x11_above)
from aeroscope.settings import DEFAULT

ROOT = Path(__file__).resolve().parents[1]
PIP = (ROOT / 'aeroscope/mini_map.py').read_text()
UI = (ROOT / 'aeroscope/ui.py').read_text()
PREF = (ROOT / 'aeroscope/preferences.py').read_text()


def test_compact_scale_unit_follows_main_app():
    for unit, suffix in [('kmh', 'km'), ('kt', 'NM'), ('mph', 'mi')]:
        label, px = compact_scale(-20.2, 9, unit)
        assert label.endswith(suffix)
        assert 1 <= px <= 76
    assert compact_scale(-20.2, 10, 'kmh')[0] != compact_scale(-20.2, 3, 'kmh')[0]


def test_x11_event_structure_and_no_surface():
    assert request_x11_above(0, True) is False
    # Actual X11 event is larger than the C client message and transports five longs.
    import ctypes
    assert ctypes.sizeof(_XEvent) >= 5 * ctypes.sizeof(ctypes.c_long)
    assert request_window_above(mock.Mock(get_surface=lambda: None), True) == 'not-ready'


def test_x11_option_is_default_and_user_toggle_is_persisted():
    assert DEFAULT['pip_always_on_top'] is True
    assert 'pip_always_on_top' in PREF
    assert "self.radar._change_setting('pip_always_on_top', value)" in PIP
    assert 'request_window_above(self, self._always_top)' in PIP


def test_no_maximize_or_minimize_buttons_in_minimap():
    assert "Gtk.WindowHandle() if hasattr(Gtk, 'WindowHandle')" in PIP
    assert "close = Gtk.Button(icon_name='window-close-symbolic')" in PIP
    assert 'set_resizable(True)' in PIP
    assert 'self.maximize()' not in PIP
    assert 'self.unmaximize()' not in PIP
    assert 'set_show_zoom_buttons(False)' in PIP
    assert "self.simple_map.get_scale().set_visible(False)" in PIP
    assert 'self._draw_compact_scale' in PIP


def test_select_double_right_click_semantics():
    simple = PIP.split('def _select(self, hexid):', 1)[1].split('def _open_on_double_click', 1)[0]
    double = PIP.split('def _open_on_double_click(self, hexid):', 1)[1].split('def _context_aircraft', 1)[0]
    assert 'self.radar.select_plane(hexid)' in simple
    assert 'show_main_window' not in simple
    assert 'show_main_window()' in double
    assert 'count == 2' in PIP
    assert 'right_click.set_button(3)' in UI
    assert 'on_context=self._context_aircraft' in PIP
    assert 'on_context=self.show_aircraft_context_menu' in UI


def test_photo_is_fetched_on_context_menu_when_missing():
    ctx = UI.split('def show_aircraft_context_menu(', 1)[1].split('def _toggle_favorite(', 1)[0]
    assert "bool(photo.get('image') or photo.get('link'))" in ctx
    assert "_('Photo unavailable')" in ctx
    assert 'self._decode_photo(hexid, cached' in ctx
    assert 'self._context_photo_waiters.setdefault(hexid, [])' in ctx
    assert 'hexid not in self.photo_pending' in ctx
    assert 'self._fetch_photo(hexid, plane.registration)' in ctx
    assert 'parent_window=parent_window' in ctx


def test_pip_uses_same_markers_and_no_new_api_calls():
    assert 'for hexid, original in self.radar.markers.items():' in PIP
    assert 'marker.marker.set_location(original.marker.get_latitude(),' in PIP
    assert 'fetch_area(' not in PIP
    assert 'fetch_global_emergencies(' not in PIP
