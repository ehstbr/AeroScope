"""Offline tests for registration watchlist and worldwide squawk lookup."""
import json

import pytest

from aeroscope import monitor


def test_normalization_duplicate_and_limit():
    a = monitor.add_favorite([], 'registration', 'pt-muj', 'Helicóptero')
    assert a[0].value == 'PT-MUJ'
    assert monitor.add_favorite(a, 'registration', 'PT-MUJ') == a
    assert monitor.normalize_favorite('icao', 'e48df5').value == 'E48DF5'
    with pytest.raises(ValueError):
        monitor.normalize_favorite('icao', 'ZZZZZZ')
    with pytest.raises(ValueError):
        monitor.add_favorite(a, 'registration', 'not a valid reg!')
    full = [monitor.Favorite('icao', f'{x:06X}') for x in range(12)]
    with pytest.raises(ValueError):
        monitor.add_favorite(full, 'icao', 'E48DF5')


def test_watchlist_roundtrip(tmp_path):
    p = tmp_path / 'config' / 'favorites.json'
    records = [monitor.Favorite('registration', 'PT-MUJ', 'Resgate')]
    monitor.save_favorites(records, p)
    assert monitor.load_favorites(p) == records
    assert json.loads(p.read_text())[0]['value'] == 'PT-MUJ'
    p.write_text('[{"kind":"registration","value":"PT-MUJ"},'
                 '{"kind":"registration","value":"PT-MUJ"},'
                 '{"kind":"icao","value":"BAD"}]')
    assert len(monitor.load_favorites(p)) == 1


def test_favorite_status_with_and_without_gps(monkeypatch):
    seen = []
    def request(url, timeout=11):
        seen.append(url)
        return {'ac': [{'hex': 'e48df5', 'r': 'PT-MUJ', 'flight': 'ARCANJO9',
                        'seen': 1.0, 'seen_pos': 0.5, 'type': 'adsb_icao'}]}
    monkeypatch.setattr(monitor, 'read_json', request)
    assert monitor.fetch_favorite(monitor.Favorite('registration','PT-MUJ'))[0] == 'active-no-position'
    assert seen[-1].endswith('/reg/PT-MUJ')
    def with_coords(url, timeout=11):
        row = request(url)['ac'][0]
        return {'ac': [{**row, 'lat': -20.1, 'lon': -44.8, 'messages': 5,
                        'mlat': [], 'tisb': [], 'rssi': -5}]}
    monkeypatch.setattr(monitor, 'read_json', with_coords)
    state, plane, callsign = monitor.fetch_favorite(monitor.Favorite('icao', 'E48DF5'))
    assert state == 'active' and plane.hex == 'e48df5' and callsign == 'ARCANJO9'
    assert seen[-1].endswith('/icao/E48DF5')


def test_offline_not_network_error(monkeypatch):
    monkeypatch.setattr(monitor, 'read_json', lambda *a, **k: {'ac': []})
    assert monitor.fetch_favorite(monitor.Favorite('registration','PT-MUJ'))[0] == 'offline'
    def fail(*a,**k):
        raise RuntimeError('network down')
    monkeypatch.setattr(monitor, 'read_json', fail)
    with pytest.raises(RuntimeError):
        monitor.fetch_favorite(monitor.Favorite('registration','PT-MUJ'))


def test_worldwide_alerts_query_three_global_endpoints(monkeypatch):
    calls = []
    def fake(url, timeout=12):
        calls.append(url)
        code = url.rsplit('/',1)[-1]
        return {'ac': [{'hex': 'e48df5' if code == '7700' else {'7600': 'a00001', '7500': 'a00002'}[code],
                        'flight': 'TEST', 'squawk': code, 'seen': 1.0,
                        'lat': 5., 'lon': -70., 'seen_pos': 0.5},
                       {'hex':'bad000', 'flight':'WRONG', 'squawk':'1234'}]}
    monkeypatch.setattr(monitor, 'read_json', fake)
    records, errors, ts = monitor.fetch_global_emergencies()
    assert len(calls) == 3
    assert [u.rsplit('/',1)[-1] for u in calls] == ['7700','7600','7500']
    assert len(records) == 3
    assert not errors
    assert all(item['aircraft'] for item in records)


def test_global_partial_errors_not_silent(monkeypatch):
    def fake(url, timeout=12):
        if url.endswith('/7600'):
            raise RuntimeError('host failed')
        return {'ac': []}
    monkeypatch.setattr(monitor, 'read_json', fake)
    rows, errors, checked = monitor.fetch_global_emergencies()
    assert not rows and '7600' in errors and checked > 0


def test_429_stops_worldwide_requests(monkeypatch):
    calls = []
    def fake(url, timeout=12):
        calls.append(url)
        raise monitor.RateLimitError('429', 180)
    monkeypatch.setattr(monitor, 'read_json', fake)
    with pytest.raises(monitor.RateLimitError):
        monitor.fetch_global_emergencies()
    assert len(calls) == 1
