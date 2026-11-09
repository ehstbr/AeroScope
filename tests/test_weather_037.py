"""NOAA station details and error isolation; no network/GTK necessary."""
from pathlib import Path
import urllib.error
import pytest
from aeroscope import weather_data

ROOT = Path(__file__).resolve().parents[1]


def test_station_metar_query(monkeypatch):
    requests = []
    def fake(url, **kw):
        requests.append(url)
        return [{'icaoId':'SBCF', 'lat':-19.62, 'lon':-43.97,
                 'rawOb':'SBCF 081200Z 18008KT 9999', 'fltCat':'VFR',
                 'obsTime':1731067200}]
    monkeypatch.setattr(weather_data, 'get_json', fake)
    row = weather_data.fetch_metar_station('sbcf')
    assert row.station == 'SBCF' and '18008KT' in row.raw
    assert requests == ['https://aviationweather.gov/api/data/metar?ids=SBCF&format=json']


def test_station_no_metar_and_validates_id(monkeypatch):
    monkeypatch.setattr(weather_data, 'get_json', lambda *_a, **_k: None)
    assert weather_data.fetch_metar_station('SBSP') is None
    with pytest.raises(ValueError):
        weather_data.fetch_metar_station('not-an-icao')


def test_independent_noaa_errors(monkeypatch):
    def fake(url, **kw):
        if '/sigmet?' in url:
            raise urllib.error.URLError('temporarily unavailable')
        return {'type':'FeatureCollection', 'features': []}
    monkeypatch.setattr(weather_data, 'get_json', fake)
    metars, sigmets, errors = weather_data.fetch_noaa_with_errors(-19.7, -43.9)
    assert metars == [] and sigmets == []
    assert 'sigmet' in errors and 'metar' not in errors


def test_noaa_is_in_airport_sidebar_and_no_rainviewer():
    ui=(ROOT/'aeroscope'/'ui.py').read_text()
    manager=(ROOT/'aeroscope'/'weather_ui.py').read_text()
    assert 'self.weather.get_airport_metar(icao)' in ui
    assert 'Checking METAR' in ui
    assert 'no active advisories in the requested area' in manager
    assert 'request failed' in manager
    assert 'fetch_noaa_with_errors' in manager
    assert 'self.radar._async(lambda: fetch_metar_station(key)' in manager
