"""NOAA cadence and integration regressions (headless, no network or GTK)."""
from pathlib import Path

from aeroscope.noaa_schedule import (
    MIN_REGION_GAP_SECONDS, REGION_CHANGE_NM, weather_refresh_decision,
)

ROOT = Path(__file__).resolve().parents[1]


def test_first_region_is_fetched_immediately_even_during_startup():
    assert weather_refresh_decision(1, 0, (-19.7, -43.9), None, 0) == (True, 0)


def test_same_region_does_not_repeat_before_fifteen_minutes():
    anchor = (-19.7, -43.9)
    assert weather_refresh_decision(40, 930, anchor, anchor, 20) == (False, 0)
    assert weather_refresh_decision(930, 930, anchor, anchor, 20) == (True, 0)


def test_small_move_reuses_metar_stations_already_covered_by_bbox():
    anchor = (-19.7, -43.9)
    shifted = (-19.5, -43.9)  # ~12 nm, not a new NOAA data region
    assert weather_refresh_decision(50, 900, shifted, anchor, 20) == (False, 0)


def test_new_region_refreshes_before_periodic_deadline():
    anchor = (-19.7, -43.9)
    new_region = (-17.0, -43.9)
    assert weather_refresh_decision(60, 900, new_region, anchor, 20) == (True, 0)


def test_fast_panning_is_throttled_but_schedules_retry():
    anchor = (-19.7, -43.9)
    new_region = (-17.0, -43.9)
    due, wait = weather_refresh_decision(26, 930, new_region, anchor, 20)
    assert due is False and 8 < wait <= MIN_REGION_GAP_SECONDS
    assert weather_refresh_decision(35.1, 930, new_region, anchor, 20) == (True, 0)


def test_first_snapshot_and_both_maps_wired_to_weather_scheduler():
    radar = (ROOT / 'aeroscope' / 'ui.py').read_text()
    mini = (ROOT / 'aeroscope' / 'mini_map.py').read_text()
    weather = (ROOT / 'aeroscope' / 'weather_ui.py').read_text()
    assert 'self.weather.region_updated()' in radar
    assert radar.count('self.weather.region_updated()') >= 2
    assert 'self.radar._view_settled()' in mini
    assert 'self._next_noaa[kind] = completed_at + self.NOAA_SECONDS' in weather
    assert 'self._schedule_deferred_region(delay)' in weather
    assert 'self.tick()' in weather.split('    def _noaa_done(self, result, error, location=None, products=', 1)[1].split('def cached_metar', 1)[0]
    assert 'if vp is None:  # no weather polling in tray-only mode' in weather
