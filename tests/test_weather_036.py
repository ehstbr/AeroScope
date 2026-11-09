"""Pure API/parser and structural regressions; no GTK/display or HTTP needed."""
from pathlib import Path
import pytest
from aeroscope.weather_data import (
    fetch_metar_station, noaa_url, noaa_bbox, parse_metars,
    parse_sigmets, get_json, fetch_noaa,
)
from aeroscope.settings import DEFAULT

ROOT = Path(__file__).resolve().parents[1]


def test_rainviewer_is_not_in_application():
    src = '\n'.join((ROOT / 'aeroscope' / n).read_text() for n in
                    ('ui.py', 'settings.py', 'preferences.py', 'weather_data.py', 'weather_ui.py'))
    assert 'rainviewer' not in src.lower()
    assert 'weather_rain' not in src


def test_noaa_bbox_and_product_urls():
    assert noaa_bbox(-19.7,-43.9)==(-22.7,-47.4,-16.7,-40.4)
    u = noaa_url('metar', noaa_bbox(-19.7,-43.9))
    assert 'aviationweather.gov/api/data/metar?' in u
    assert 'format=geojson' in u
    assert 'bbox=' in u
    with pytest.raises(ValueError):
        noaa_url('unknown', (0,0,0,0))


def test_metar_decode_and_invalid_points():
    sample={'type':'FeatureCollection','features':[
        {'type':'Feature','geometry':{'type':'Point','coordinates':[-43.97,-19.62]},'properties':{
            'icaoId':'SBCF','rawOb':'SBCF 081200Z 18008KT 9999 FEW010 26/22 Q1015','fltCat':'VFR', 'obsTime':'2026-11-08T12:00:00Z'}},
        {'type':'Feature','geometry':{'type':'Point','coordinates':[999,999]},'properties':{'icaoId':'INVALID'}}]}
    rows = parse_metars(sample)
    assert len(rows)==1
    assert rows[0].station=='SBCF'
    assert rows[0].category=='VFR'
    assert '18008KT' in rows[0].raw


def test_sigmet_geojson_polygon_and_multipolygon():
    poly=[[-43,-20],[-42,-20],[-42,-19],[-43,-20]]
    data={'type':'FeatureCollection','features':[
        {'geometry':{'type':'Polygon','coordinates':[poly]},'properties':{'hazard':'TS','rawSigmet':'THUNDERSTORMS'}},
        {'geometry':{'type':'MultiPolygon','coordinates':[[poly]]},'properties':{'hazard':'TURB'}}]}
    rows=parse_sigmets(data)
    assert len(rows)==2
    assert rows[0].rings[0][0]==(-20.,-43.)
    assert rows[0].text=='THUNDERSTORMS'
    assert rows[1].name=='TURB'


def test_opt_in_and_animated_zoom_wired():
    assert DEFAULT['weather_metar'] is False
    assert DEFAULT['weather_sigmet'] is False
    ui=(ROOT/'aeroscope'/'ui.py').read_text()
    mini=(ROOT/'aeroscope'/'mini_map.py').read_text()
    for src in (ui, mini):
        assert 'self.map.set_animate_zoom(True)' in src
        assert 'self.map.zoom_in()' in src
        assert 'self.map.zoom_out()' in src
    assert "visual_menu.append_submenu(_('Weather'), weather_menu)" in ui
    assert 'self.weather.settings_changed()' in ui
    assert 'self.weather_view = self.radar.weather.attach(' in mini


def test_weather_manager_disabled_in_tray():
    src = (ROOT/'aeroscope'/'weather_ui.py').read_text()
    assert 'if vp is None:  # no weather polling in tray-only mode' in src
    assert "metar = bool(opts.get('weather_metar'))" in src
    assert "sigmet = bool(opts.get('weather_sigmet'))" in src
