"""Regression tests for matching airport/station inspector controls."""
import ast
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text()


def _method(name):
    module = ast.parse(SOURCE)
    radar_class = next(cls for cls in module.body if isinstance(cls, ast.ClassDef)
                       and any(isinstance(n, ast.FunctionDef) and n.name == name for n in cls.body))
    fn = next(n for n in radar_class.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SOURCE, fn)


def test_location_header_has_center_and_close_icons():
    body = _method('_append_location_header')
    assert "icon_button('find-location-symbolic'" in body
    assert "icon_button('window-close-symbolic'" in body
    assert "self._pan_to_aircraft(lat, lon)" in body
    assert 'self._clear_selected()' in body
    assert "title.set_ellipsize(Pango.EllipsizeMode.END)" in body
    assert "title.set_tooltip_text(name)" in body


def test_station_and_airport_share_the_same_controls():
    body = _method('_render_details')
    assert "self._append_location_header(_('Weather station · ') + metar.station," in body
    assert "self._append_location_header(name, lat, lon, _('airport'), airport_code=iata)" in body
    assert "Gtk.Button(label='Centralizar estação')" not in body
    assert "Gtk.Button(label='Centralizar aeroporto')" not in body
    assert "self.map.center_on(lat, lon)" not in body
    assert "Gtk.Button(label=_('View arrivals and departures'))" in body


def test_clearing_selection_deselects_both_station_and_airport():
    body = _method('_clear_selected')
    assert 'self.selected_weather_station = None' in body
    assert 'self.selected_airport = None' in body
    assert 'self._render_details()' in body
