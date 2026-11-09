"""Regressions for live favorites and initial non-blocking monitor checks."""
from dataclasses import dataclass
from pathlib import Path
import ast

from aeroscope.monitor import normalize_favorite, live_favorite_checks

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class Plane:
    hex: str = 'e48df5'
    registration: str = 'PT-MUJ'
    flight: str = 'ARCANJO9'
    seen: float = 0.8
    lat: float = -20.12
    lon: float = -44.88


def test_live_radar_immediately_matches_registration_and_icao():
    favorites = [normalize_favorite('registration', 'PT-MUJ'),
                 normalize_favorite('icao', 'E48DF5')]
    checks = live_favorite_checks(favorites, [Plane()], checked_at=12_345.0)
    assert set(checks) == {favorites[0].key, favorites[1].key}
    assert all(result[0] == 'active' and result[2] == 12_345.0
               for result in checks.values())


def test_missing_or_old_plane_does_not_mean_offline():
    favorites = [normalize_favorite('registration', 'PT-MUJ')]
    assert live_favorite_checks(favorites, [], checked_at=123) == {}
    assert live_favorite_checks(favorites, [Plane(seen=200)], checked_at=123) == {}


def test_startup_monitor_is_installed_independent_of_splash_and_visible_tab():
    ui = (ROOT / 'aeroscope' / 'ui.py').read_text()
    monitor = (ROOT / 'aeroscope' / 'monitor_ui.py').read_text()
    # Syntax is parsed to catch malformed callbacks, not just raw keyword matches.
    ast.parse(ui)
    ast.parse(monitor)
    assert 'GLib.timeout_add(1700, self.monitor_panel.start_initial_checks)' in ui
    assert 'def start_initial_checks(self):' in monitor
    assert 'self._refresh_emergencies(force=True)' in monitor
    assert 'self._queue_startup_favorites()' in monitor
    assert 'def _start_startup_favorites(self):' in monitor
    assert 'if self._startup_pending:' in monitor
    assert 'self.monitor_panel.update_from_live(planes)' in ui


def test_emergency_initial_lookup_not_gated_by_periodic_preference():
    monitor = (ROOT / 'aeroscope' / 'monitor_ui.py').read_text()
    initial = monitor.split('def start_initial_checks(self):', 1)[1].split(
        'def _queue_startup_favorites', 1)[0]
    assert "settings['monitor_emergencies']" not in initial
    periodic = monitor.split('def _auto_refresh(self):', 1)[1]
    assert "self.radar.settings['monitor_emergencies']" in periodic
