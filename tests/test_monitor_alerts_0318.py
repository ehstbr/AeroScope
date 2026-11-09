"""Alert and monitoring regression tests, without GTK or network dependencies."""

from types import SimpleNamespace

from aeroscope.monitor_alerts import AlertTransitions, likely_airborne
from aeroscope.settings import DEFAULT, load


def _plane(altitude=8000, speed=120, on_ground=None):
    return SimpleNamespace(altitude_ft=altitude, speed_kts=speed, on_ground=on_ground)


def test_airborne_heuristic_is_conservative():
    assert likely_airborne(_plane())
    assert not likely_airborne(_plane(300, 10))
    assert not likely_airborne(_plane(None, 160))
    assert not likely_airborne(None)


def test_favorite_needs_two_offline_readings_and_airborne_return():
    tracker = AlertTransitions()
    # Initial sample, including a flying aircraft, never causes notifications.
    assert tracker.favorites_updated({'registration:PR-ABC': ('active', _plane(), 1, '')}) == []
    assert tracker.favorites_updated({'registration:PR-ABC': ('offline', None, 2, '')}) == []
    # One transient missing sample must not trigger a notification.
    assert tracker.favorites_updated({'registration:PR-ABC': ('active', _plane(), 3, '')}) == []
    tracker.favorites_updated({'registration:PR-ABC': ('offline', None, 4, '')})
    tracker.favorites_updated({'registration:PR-ABC': ('offline', None, 5, '')})
    assert len(tracker.favorites_updated({'registration:PR-ABC': ('active', _plane(), 6, '')})) == 1
    assert tracker.favorites_updated({'registration:PR-ABC': ('active', _plane(), 7, '')}) == []


def test_favorite_going_from_explicit_ground_to_likely_flight():
    tracker = AlertTransitions()
    key = 'registration:PR-MBA'
    assert tracker.favorites_updated({key: ('active', _plane(None, 5, True), 1, '')}) == []
    assert len(tracker.favorites_updated({key: ('active', _plane(1200, 95), 2, '')})) == 1
    assert tracker.favorites_updated({key: ('active', _plane(1800, 110), 3, '')}) == []


def test_explicit_ground_is_preserved_by_aircraft_parser():
    from aeroscope.data import parse_aircraft
    plane = parse_aircraft({'ac': [{'hex': 'e48df5', 'lat': -20.1, 'lon': -44.8,
                                    'alt_baro': 'ground', 'gs': 4.5}]})[0]
    assert plane.on_ground is True
    assert plane.altitude_ft is None


def test_favorite_error_is_not_offline_and_ground_is_not_flying():
    tracker = AlertTransitions()
    tracker.favorites_updated({'icao:E48DF5': ('error', None, 1, '')})
    tracker.favorites_updated({'icao:E48DF5': ('offline', None, 2, '')})
    tracker.favorites_updated({'icao:E48DF5': ('offline', None, 3, '')})
    assert tracker.favorites_updated({'icao:E48DF5': ('active', _plane(None, 40), 4, '')}) == []
    assert tracker.favorites_updated({'icao:E48DF5': ('active', _plane(), 5, '')}) == []


def test_emergencies_first_poll_is_baseline_followup_is_one_notification():
    tracker = AlertTransitions()
    a = {'hex': 'e48df5', 'squawk': '7700', 'flight': 'TEST1'}
    b = {'hex': 'abc111', 'squawk': '7600', 'flight': 'TEST2'}
    assert tracker.emergencies_updated([a], {}, now=0) == []
    assert tracker.emergencies_updated([a, b], {}, now=20) == [b]
    assert tracker.emergencies_updated([a, b], {}, now=40) == []
    assert tracker.emergencies_updated([a], {}, now=50) == []
    assert tracker.emergencies_updated([a, b], {}, now=60) == []  # no flapping
    assert tracker.emergencies_updated([a, b], {}, now=1900) == []  # continuously present


def test_emergency_failed_code_does_not_reset_baseline():
    tracker = AlertTransitions()
    a = {'hex': 'e48df5', 'squawk': '7700'}
    b = {'hex': 'abc111', 'squawk': '7700'}
    tracker.emergencies_updated([a], {}, now=0)
    tracker.emergencies_updated([], {'7700': 'timeout'}, now=5)
    assert tracker.emergencies_updated([a, b], {}, now=10) == [b]


def test_monitor_preferences_have_safe_defaults():
    assert DEFAULT['monitor_emergencies'] is True  # 0.3.22 default: background alerts enabled
    assert DEFAULT['monitor_favorites'] is True
    assert DEFAULT['sound_emergencies'] is False
    assert DEFAULT['favorites_interval'] == DEFAULT['emergencies_interval'] == 120


def test_monitor_ui_and_preference_hooks_are_present():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1]
    monitor_ui = (src / 'aeroscope/monitor_ui.py').read_text()
    prefs = (src / 'aeroscope/preferences.py').read_text()
    assert "icon_name='list-add-symbolic'" in monitor_ui
    assert "self.add_revealer" in monitor_ui
    assert "self._transitions.emergencies_updated" in monitor_ui
    assert "self._transitions.favorites_updated" in monitor_ui
    assert "settings['emergencies_interval']" in prefs
    assert "settings['favorites_interval']" in prefs
    assert "settings['sound_emergencies']" in prefs
