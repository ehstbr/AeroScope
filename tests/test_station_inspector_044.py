from pathlib import Path
import ast
from aeroscope.airport_weather_badge import metar_badge
from aeroscope.weather_data import Metar

ROOT=Path(__file__).resolve().parents[1]

def test_station_pictogram_asset_exists():
    svg=(ROOT/'assets'/'weather-station.svg').read_text()
    assert '<svg ' in svg and '</svg>' in svg
    assert 'circle' in svg and 'path' in svg  # anemometer / station mast

def test_weather_station_is_not_a_generic_airport_button():
    src=(ROOT/'aeroscope'/'weather_ui.py').read_text()
    ast.parse(src)
    assert "button.add_css_class('weather-station-marker')" in src
    assert "assets' / 'weather-station.svg'" in src
    assert "Gtk.Label(label=metar.station)" in src
    assert 'Adw.MessageDialog.new(' not in src
    assert 'radar.select_weather_station(metar)' in src
    assert 'radar.select_airport(matching_airport)' in src

def test_station_inspector_uses_same_metar_decoder_as_airport():
    src=(ROOT/'aeroscope'/'ui.py').read_text()
    ast.parse(src)
    assert 'def select_weather_station(self, metar):' in src
    assert 'def _append_metar_report(self, metar):' in src
    assert 'self._append_metar_report(metar)' in src
    assert "Gtk.Expander(label=_('View original METAR (technical code)'))" in src
    assert 'self.selected_weather_station = None' in src

def test_geolocation_toasts_follow_visible_map():
    ui=(ROOT/'aeroscope'/'ui.py').read_text()
    pip=(ROOT/'aeroscope'/'mini_map.py').read_text()
    ast.parse(pip)
    assert 'self.toast = Adw.ToastOverlay()' in pip
    assert 'pip.get_visible()' in ui and 'pip.notify(text)' in ui
    assert "geo.connect('clicked', lambda *_: self.radar.locate())" in pip

def test_category_only_when_provided():
    metar=Metar('SBBW',-14.0,-52.0,'METAR SBBW 101200Z 00000KT CAVOK','N/D','2026-11-08')
    assert metar_badge(metar)=='METAR'
