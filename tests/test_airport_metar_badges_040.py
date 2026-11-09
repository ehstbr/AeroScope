"""Regression tests for airport IATA labels, NOAA badge safety and attribution."""
from pathlib import Path

from aeroscope.airport_weather_badge import (
    airport_marker_text, airport_metar_tooltip, metar_category,
    station_marker_text,
)
from aeroscope.weather_data import Metar, parse_metars

ROOT = Path(__file__).resolve().parents[1]


def test_label_and_category_are_taken_only_from_genuine_report():
    report = Metar('SBCF', -19.6, -43.9, 'SBCF 081200Z', 'IFR', '12:00 UTC')
    assert airport_marker_text('cnf', report, metar_enabled=True) == 'CNF · IFR'
    assert airport_marker_text('cnf', report, metar_enabled=False) == 'CNF'
    assert airport_marker_text('cnf', None, metar_enabled=True) == 'CNF'
    assert station_marker_text('SBCF', report) == 'SBCF · IFR'
    assert 'METAR NOAA: IFR' in airport_metar_tooltip('Confins','CNF','SBCF',report,enabled=True)


def test_unknown_category_never_claims_vfr():
    report = Metar('SNDV', -20.2, -44.9, '', 'N/D', '')
    assert metar_category(report) is None
    assert airport_marker_text('DIQ', report, metar_enabled=True) == 'DIQ'
    assert 'sem observação disponível' in airport_metar_tooltip('Divinópolis','DIQ','SNDV',report,enabled=True)
    assert metar_category(Metar('SBCF',0,0,'','LIFR','')) == 'LIFR'


def test_regional_geojson_and_json_fallback_are_parsed():
    rows = parse_metars([
        {'icaoId':'SBCF','lat':-19.62,'lon':-43.97,'fltCat':'MVFR','rawOb':'SBCF ...'},
        {'icaoId':'BAD','lat':-1000,'lon':10, 'fltCat':'VFR'},
    ])
    assert len(rows) == 1 and rows[0].station == 'SBCF' and rows[0].category == 'MVFR'


def test_main_map_has_airport_badges_and_no_generic_diamonds():
    ui=(ROOT/'aeroscope'/'ui.py').read_text()
    weather=(ROOT/'aeroscope'/'weather_ui.py').read_text()
    css=(ROOT/'assets'/'style.css').read_text()
    assert "button = Gtk.Button(label='◇')" not in ui
    assert 'self._create_airport_marker_button(' in ui
    assert "category_label = Gtk.Label(label=category)" in ui
    assert 'self.weather.cached_metar(icao)' in ui
    assert 'self.radar._rebuild_airports()' in weather
    assert 'if metar.station in fixed_stations and enabled_airports:' in weather
    assert 'airport-weather-category' in css


def test_noaa_credit_only_in_about_osm_licence_retained():
    ui=(ROOT/'aeroscope'/'ui.py').read_text()
    weather=(ROOT/'aeroscope'/'weather_ui.py').read_text()
    assert 'NOAA Aviation Weather Center — METAR / SIGMET' in ui
    assert 'self.credits' not in weather
    assert "'© OpenStreetMap contributors'" in ui
    assert 'self.simple_map.get_license()' in (ROOT/'aeroscope'/'mini_map.py').read_text()
