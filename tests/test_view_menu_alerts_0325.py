"""Tests for independent clock, saved viewpoint and ICAO-linked emergencies."""
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace

from aeroscope.map_view import validated_view, load_view, save_view
from aeroscope.settings import DEFAULT
from aeroscope.alerts import classify_alert

ROOT = Path(__file__).resolve().parents[1]


def test_saved_view_round_trip_and_bounds(tmp_path):
    file = tmp_path / 'aeroscope' / 'last-map-view.json'
    assert save_view(40.6413, -73.7781, 10.5, file)
    assert load_view(file) == (40.6413, -73.7781, 10.5)
    assert json.loads(file.read_text())['lat'] == 40.6413
    assert not save_view(99, 0, 8, file)
    assert not save_view(0, 0, float('nan'), file)
    assert load_view(file) == (40.6413, -73.7781, 10.5)
    file.write_text('corrupt')
    assert load_view(file) is None
    assert validated_view({'lat': -20.13, 'lon': -44.88, 'zoom': 8}) is not None


def test_visual_switches_independent_and_persisted():
    assert DEFAULT['clock_ring'] is True
    assert DEFAULT['tower'] is False
    assert DEFAULT['tower_sweep'] is False
    src = (ROOT/'aeroscope/ui.py').read_text()
    assert "append_menu_action(visual_menu, _('Control tower mode'), 'app.toggle-tower')" in src
    assert "visual_menu.append(_('Aircraft clock'), 'app.toggle-clock')" in src
    assert "append_menu_action(visual_menu, _('Rotating sweep'), 'app.toggle-sweep')" in src
    assert 'Gio.SimpleAction.new_stateful(' in src
    assert "elif key == 'clock_ring':" in src
    assert 'self.get_application().sync_visual_action(key, value)' in src
    assert 'self.clock_decoration.set_draw_func(self._draw_clock_overlay)' in src
    clock = src.split('def _draw_clock_overlay(',1)[1].split('def _draw_radar(',1)[0]
    assert "self.settings['clock_ring']" in clock
    assert "self.settings['tower']" not in clock
    draw_tower = src.split('def _draw_radar(',1)[1].split('def show_preferences(',1)[0]
    assert 'self._draw_relative_clock(' not in draw_tower
    pref = (ROOT/'aeroscope/preferences.py').read_text()
    assert 'Selected aircraft clock' in pref


def test_view_saved_at_close_and_not_reset_by_geo_auto():
    src = (ROOT/'aeroscope/ui.py').read_text()
    assert "self.connect('close-request', self._on_close_requested)" in src
    assert "self._persist_map_view()" in src.split("def _on_close_requested", 1)[1].split("def _persist_map_view", 1)[0]
    assert 'self.viewport.get_zoom_level()' in src.split('def _persist_map_view(',1)[1].split('def _load_style(',1)[0]
    assert 'self._restored_map_view = load_view()' in src
    assert 'self._restored_map_view[2] if self._restored_map_view else 8' in src
    assert 'if not self.demo and self._regional_tracking_started and self._restored_map_view is None:' in src


def test_global_alerts_crosslinked_by_exact_icao24_only():
    src = (ROOT/'aeroscope/ui.py').read_text()
    monitor = (ROOT/'aeroscope/monitor_ui.py').read_text()
    assert 'effective_alert(' in src
    assert 'from .emergency_match import effective_alert' in src
    assert 'marker.set_alert(self._effective_aircraft_alert(plane)' in src
    assert 'self._effective_aircraft_alert(p).level' in src
    assert 'alert = self._effective_aircraft_alert(plane)' in src
    assert 'self.radar._refresh_visible_alerts()' in monitor
    assert classify_alert('7600').level == 'warning'
    assert classify_alert('7700').level == 'critical'
    assert classify_alert('2000').level == 'none'


def test_world_emergency_does_not_mark_an_unrelated_aircraft():
    from aeroscope.emergency_match import effective_alert
    regional = SimpleNamespace(hex='e07d3a', squawk='2000', emergency='')
    global_rows = [{'hex':'aabbcc', 'squawk':'7600'}, {'hex':'000000', 'squawk':'7700'}]
    assert effective_alert(regional, global_rows, checked_at=1000, now=1020).level == 'none'
    assert effective_alert(regional, [{'hex':'E07D3A','squawk':'7600'}],
                           checked_at=1000, now=1020).level == 'warning'
    assert effective_alert(regional, [{'hex':'e07d3a','squawk':'7700'}],
                           checked_at=1000, now=1020).level == 'critical'
    assert effective_alert(regional, [{'hex':'e07d3a','squawk':'7700'}],
                           checked_at=1000, now=2000).level == 'none'


def test_local_priority_does_not_get_downgraded():
    from aeroscope.emergency_match import effective_alert
    regional = SimpleNamespace(hex='e07d3a', squawk='7500', emergency='')
    assert effective_alert(regional, [{'hex':'e07d3a','squawk':'7600'}],
                           checked_at=1000, now=1020).level == 'critical'
