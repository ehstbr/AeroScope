"""Regression tests for moving virtual target and favorite-session observation log."""
import ast
from dataclasses import dataclass
from pathlib import Path
from aeroscope.favorite_history import SessionFavoriteHistory, classify_observation
from aeroscope.monitor import normalize_favorite
from aeroscope.tower_radar import crossed_moving_target


@dataclass
class Plane:
    altitude_ft: int = 21000
    speed_kts: int = 320
    on_ground: bool | None = False


F = normalize_favorite('registration', 'PT-MUJ')


def check(state, plane, when):
    return {F.key: (state, plane, when, '')}


def test_stationary_virtual_target_crossing():
    assert crossed_moving_target(55, 62, 60, 60)
    assert not crossed_moving_target(55, 58, 60, 60)


def test_crossing_estimated_position_not_old_marker():
    # The icon is still frozen at 200 degrees. The moving virtual aircraft
    # travels from 60 to 61 degrees; the beam catches it at ~60.5 degrees.
    assert crossed_moving_target(58, 63, 60, 61)
    assert not crossed_moving_target(58, 63, 200, 200)


def test_virtual_target_catches_beam_and_north_wrap():
    assert crossed_moving_target(10, 12, 9, 14)
    assert crossed_moving_target(357, 3, 359, 0)
    assert not crossed_moving_target(357, 3, 200, 201)


def test_ignore_unstable_viewport_and_resume_after_suspend():
    assert not crossed_moving_target(0, 180, 10, 10)
    assert not crossed_moving_target(5, 8, 30, 210)
    assert crossed_moving_target(5, 8, 30, 210, full_turn=True)


def test_history_uses_real_observations_not_offline_on_local_miss():
    log = SessionFavoriteHistory()
    favorites = {F.key: F}
    assert log.observe({}, favorites) == []
    assert len(log.observe(check('active', Plane(), 100), favorites)) == 1
    assert log.active[F.key]['state'] == 'airborne'
    assert log.observe({}, favorites) == []
    assert log.observe(check('offline', None, 110), favorites) == []
    assert log.observe(check('offline', None, 110), favorites) == []  # same scan twice
    assert log.active[F.key]['state'] == 'airborne'
    assert len(log.observe(check('offline', None, 120), favorites)) == 1
    assert log.active[F.key]['state'] == 'offline'
    assert len(log.ended()) == 1
    assert log.ended()[0]['ended_at'] == 120


def test_history_ground_and_returning_in_flight():
    log = SessionFavoriteHistory()
    favorites = {F.key: F}
    log.observe(check('active', Plane(on_ground=True, speed_kts=0), 100), favorites)
    assert log.active[F.key]['state'] == 'ground'
    log.observe(check('error', None, 101), favorites)
    assert log.active[F.key]['state'] == 'ground'
    log.observe(check('active', Plane(), 102), favorites)
    assert log.active[F.key]['state'] == 'airborne'
    assert log.ended()[0]['state'] == 'ground'
    log.remove(F.key, 110)
    assert len(log.ended()) == 2
    assert log.active == {}


def test_history_ignores_stale_global_response():
    log = SessionFavoriteHistory()
    favorites = {F.key: F}
    log.observe(check('active', Plane(), 100), favorites)
    log.observe(check('active', Plane(on_ground=True, speed_kts=0), 90), favorites)
    assert log.active[F.key]['state'] == 'airborne'


def test_classification_not_takeoff_claim():
    assert classify_observation('active', Plane()) == 'airborne'
    assert classify_observation('active', Plane(on_ground=True, speed_kts=0)) == 'ground'
    assert classify_observation('active', Plane(on_ground=None, speed_kts=5, altitude_ft=0)) == 'tracked'
    assert classify_observation('active-no-position', None) == 'no_position'
    assert classify_observation('offline', None) == 'offline'
    assert classify_observation('error', None) is None


def test_ui_tracks_moving_virtual_point_not_marker_for_scan():
    src = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text()
    ast.parse(src)
    tick = src.split('def _tower_sweep_tick(self):', 1)[1].split('def _tower_ring_distance_nm(', 1)[0]
    assert 'virtual.sample(previous_time)' in tick
    assert 'virtual.sample(now)' in tick
    assert 'crossed_moving_target(previous, angle,' in tick
    assert '_sweep_marker_bearing(marker)' not in tick


def test_favorites_history_toggle_same_as_emergencies():
    src = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'monitor_ui.py').read_text()
    ast.parse(src)
    assert 'self.show_favorite_history = Gtk.ToggleButton()' in src
    assert "self.show_favorite_history.set_icon_name('document-open-recent-symbolic')" in src
    assert 'self._favorite_history.observe(checks,' in src
    assert "self.show_favorite_history.get_active()" in src
