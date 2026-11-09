"""AeroScope 0.3.51: persistent METAR bookmarks and new-report-only notifications."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from aeroscope.metar_watch import MetarChangeTracker, metar_fingerprint
from aeroscope.station_favorites import (
    load_station_favorites, save_station_favorites, normalized_station,
)
from aeroscope.airport_favorites import (
    load_airport_favorites, save_airport_favorites,
)
from aeroscope.weather_data import Metar, display_metar_time, fetch_metar_stations
from aeroscope.settings import DEFAULT

ROOT=Path(__file__).resolve().parents[1]


def metar(raw, category='VFR'):
    return Metar('SNDV',-20.1,-44.9,raw,category,'09/11/2026 12:00 UTC',{})


def test_metar_first_observation_is_baseline_and_repeated_reports_are_silent():
    watcher=MetarChangeTracker()
    report=metar('METAR SNDV 091200Z 09006KT CAVOK')
    assert watcher.observe('SNDV', report)==(False,None)
    assert watcher.observe('SNDV', report)==(False,None)
    # White-space normalization prevents false alerts for provider formatting changes.
    assert watcher.observe('SNDV',metar(' METAR  SNDV 091200Z 09006KT CAVOK '))==(False,None)
    assert watcher.observe('SNDV', None)==(False,None)  # outage is not a change
    assert watcher.observe('SNDV', metar('METAR SNDV 091300Z 10007KT CAVOK'))==(True,'VFR')
    assert watcher.observe('SNDV', metar('METAR SNDV 091300Z 10007KT CAVOK'))==(False,None)
    assert watcher.observe('SNDV', metar('METAR SNDV 091400Z 12009KT BKN005','IFR'))==(True,'VFR')
    watcher.retain({'SBCF'})
    assert watcher.observe('SNDV',metar('METAR SNDV 091500Z 10006KT CAVOK'))==(False,None)


def test_timestamp_change_alone_does_not_trigger_new_bulletin():
    watcher=MetarChangeTracker()
    old=metar('METAR SNDV 091200Z CAVOK')
    new=Metar(old.station,old.lat,old.lon,old.raw,old.category,'09/11/2026 12:20 UTC',{})
    assert watcher.observe('SNDV',old)==(False,None)
    assert watcher.observe('SNDV',new)==(False,None)
    assert metar_fingerprint(old)==metar_fingerprint(new)


def test_saved_stations_roundtrip_and_malformed_data_are_ignored(tmp_path):
    file=tmp_path/'favorite_stations.json'
    save_station_favorites({'sndv':(-20.1,-44.9),'SBCF':(-19.63,-43.97)},file)
    assert load_station_favorites(file)=={'SNDV':(-20.1,-44.9),'SBCF':(-19.63,-43.97)}
    assert not list(tmp_path.glob('*.tmp'))
    assert normalized_station('sndv')=='SNDV'
    for bad in ('NANANA','ABC','', 'A/B1'):
        with pytest.raises(ValueError):
            normalized_station(bad)
    file.write_text(json.dumps([{'icao':'SNDV','lat':-20.1,'lon':-44.9},
                                {'icao':'AAAA','lat':999,'lon':0}, {'icao':'INVALID'}]))
    assert load_station_favorites(file)=={'SNDV':(-20.1,-44.9)}


def test_saved_airports_independent_from_stations(tmp_path):
    ap=tmp_path/'airports.json'
    save_airport_favorites({'CNF','DIQ'},ap)
    assert load_airport_favorites(ap)=={'CNF','DIQ'}
    assert DEFAULT['monitor_metar_favorites'] is True
    assert DEFAULT['notify_metar_changes'] is True


def test_noaa_epoch_and_iso_times_are_utc():
    assert display_metar_time(1731067200)=='08/11/2024 12:00 UTC'
    assert display_metar_time('2026-11-09T12:00:00Z')=='09/11/2026 12:00 UTC'
    assert display_metar_time('')==''


def test_bookmarks_wired_into_map_sidebar_and_background_poll():
    ui=(ROOT/'aeroscope/ui.py').read_text()
    weather=(ROOT/'aeroscope/weather_ui.py').read_text()
    monitor=(ROOT/'aeroscope/monitor_ui.py').read_text()
    preferences=(ROOT/'aeroscope/preferences.py').read_text()
    for path in ('aeroscope/ui.py','aeroscope/weather_ui.py','aeroscope/monitor_ui.py'):
        ast.parse((ROOT/path).read_text())
    assert 'self.select_airport(iata)  # Right click opens the inspector, too.' in ui
    assert 'self.select_weather_station(metar)  # Right click also opens the inspector.' in ui
    assert "item(_('Center aircraft on map')" in ui
    assert "item(_('Center airport on map')" in ui
    assert "item(_('Center weather station on map')" in ui
    assert 'self._render_metar_favorite(' in monitor
    assert 'report.raw' not in monitor
    assert "self.refresh_fav_btn.connect('clicked', self._refresh_all_favorites)" in monitor
    assert 'self.refresh_favorite_metars()' in weather
    assert 'self._queue_sigmet_targets()' in weather
    assert 'if vp is None:  # no weather polling in tray-only mode' in weather
    assert "self._favorite_tracker.observe(code, report)" in weather
    assert "notification_id='metar-' + code" in weather
    assert "title=_('Favorite airport and station METARs')" in preferences


def test_noaa_station_without_coordinates_uses_saved_position(monkeypatch):
    from aeroscope import weather_data
    monkeypatch.setattr(weather_data, 'get_json', lambda *args, **kwargs: [
        {'icaoId':'SNDV','rawOb':'METAR SNDV 091200Z CAVOK','fltCat':'VFR',
         'obsTime':'2026-11-09T12:00:00Z'},
    ])
    rows=fetch_metar_stations(['SNDV'],fallback_positions={'SNDV':(-20.15,-44.88)})
    assert len(rows)==1
    assert rows[0].station=='SNDV' and rows[0].lat==-20.15
    assert rows[0].observed=='09/11/2026 12:00 UTC'
