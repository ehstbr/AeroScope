"""Regression checks for navigation shortcuts and weather-card centering."""
import ast
from pathlib import Path

from aeroscope.keyboard_shortcuts import keyboard_command, shortcut_groups

ROOT = Path(__file__).resolve().parents[1]


def test_keyboard_bindings_require_alt_and_use_english_initials():
    expected = {'plus': 'zoom-in', 'equal': 'zoom-in', 'KP_Add': 'zoom-in',
                'minus': 'zoom-out', 'KP_Subtract': 'zoom-out',
                'period': 'locate', 'KP_Decimal': 'locate',
                'f': 'search', 'l': 'locate', 't': 'tower', 's': 'sweep',
                'm': 'metar', 'p': 'pip', 'b': 'bookmarks', 'e': 'emergencies'}
    for key, action in expected.items():
        assert keyboard_command(key, alt=True) == action
        assert keyboard_command(key) is None, f'{key} must not trigger without Alt'
    assert keyboard_command('a', alt=True) == 'advisories'
    assert keyboard_command('v', alt=True) == 'visible'
    assert keyboard_command('a', ctrl=True) is None
    assert keyboard_command('v', ctrl=True) is None
    assert keyboard_command('c', ctrl=True) is None
    assert keyboard_command('F11', ctrl=False) is None  # Handled by Gio accelerator
    assert keyboard_command('F1', ctrl=False) is None
    assert keyboard_command('f', ctrl=True) is None
    assert keyboard_command('f', ctrl=True, alt=True) is None


def test_alt_shortcuts_work_when_search_has_focus_without_hijacking_text_edits():
    for key in ('period', 'plus', 'minus', 'f', 't', 'm', 's', 'l'):
        assert keyboard_command(key, alt=True, editing=True) is not None
    # Universal editing combinations are never stolen, even without focus.
    for key in ('a', 'c', 'v'):
        assert keyboard_command(key, ctrl=True, editing=True) is None
        assert keyboard_command(key, ctrl=True, editing=False) is None
    for key in ('e', 'b', 'p'):
        assert keyboard_command(key, alt=True, editing=True) is not None
        assert keyboard_command(key, ctrl=True, editing=True) is None
    for key in ('period', 'plus', 'minus', 'question', 'f', 't', 'm', 'a'):
        assert keyboard_command(key, editing=True) is None
    assert keyboard_command('a', alt=True, editing=True) == 'advisories'
    assert keyboard_command('v', alt=True, editing=True) == 'visible'
    assert keyboard_command('f', ctrl=True, alt=True) is None
    assert keyboard_command('f', alt=True, super_key=True) is None
    assert keyboard_command('z', alt=True) is None


def test_shortcut_help_has_all_actions_and_correct_modifiers():
    keys = {entry[1] for _name, entries in shortcut_groups() for entry in entries}
    assert {'<Alt>plus', '<Alt>minus', '<Alt>period', 'F11', 'F1',
            '<Alt>t', '<Alt>s', '<Alt>m', '<Alt>a',
            '<Alt>v'} <= keys
    assert '<Control>a' not in keys
    assert '<Control>c' not in keys
    assert '<Control>v' not in keys
    assert '<Control>f' not in keys
    ui = (ROOT/'aeroscope/ui.py').read_text()
    assert "'app.preferences', ['<Alt>comma']" in ui
    assert "'app.quit', ['<Alt>q']" in ui
    assert all(key.startswith('<Alt>') or key in ('F1', 'F11', 'Escape') for key in keys)


def test_shortcuts_window_has_only_one_native_titlebar():
    window_code = (ROOT/'aeroscope/keyboard_shortcuts_window.py').read_text()
    assert "title=_('Keyboard shortcuts')" in window_code
    assert 'root.append(header)' not in window_code
    assert 'Gtk.HeaderBar()' not in window_code


def test_startup_and_empty_map_click_return_focus_to_map():
    ui = (ROOT/'aeroscope/ui.py').read_text()
    assert 'self.map.set_focusable(True)' in ui
    assert 'self.map.grab_focus()' in ui
    assert "self.connect('map', self._focus_map_on_first_show)" in ui


def test_center_controls_match_aircraft_widget_style():
    weather = (ROOT/'aeroscope/floating_widget.py').read_text()
    plane = (ROOT/'aeroscope/aircraft_widget.py').read_text()
    for code in (weather, plane):
        ast.parse(code)
        assert "Gtk.Button(icon_name='find-location-symbolic')" in code
        assert "self.center_button.add_css_class('dashboard-widget-button')" in code
        assert "self.center_button.add_css_class('flat')" in code
    assert 'self.controller.center_location(self.kind, self.code)' in weather
    assert "top.append(self.center_button)" in weather
    assert weather.index('top.append(self.center_button)') < weather.index('top.append(close)')


def test_center_supports_stations_without_favorites():
    controller = (ROOT/'aeroscope/dashboard.py').read_text()
    ui = (ROOT/'aeroscope/ui.py').read_text()
    assert 'self._card_position(card, metar)' in controller
    assert 'self.radar._center_station(code, position=position)' in controller
    assert 'def _center_station(self, code, position=None)' in ui
    assert 'self._pan_to_aircraft(lat, lon)' in ui


def test_map_selection_highlights_both_locations_and_click_pans():
    ui = (ROOT/'aeroscope/ui.py').read_text()
    weather = (ROOT/'aeroscope/weather_ui.py').read_text()
    css = (ROOT/'assets/style.css').read_text()
    assert 'code=iata: self._center_airport(code)' in ui
    assert 'radar._pan_to_aircraft(metar.lat, metar.lon)' in weather
    assert 'view.sync_selection()' in ui
    assert '.airport-marker.selected-location' in css
    assert '.weather-station-marker.selected-location' in css
