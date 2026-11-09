"""Static regressions to ensure the 0.3.29 UI interactions stay connected."""
from pathlib import Path
import ast

BASE = Path(__file__).resolve().parents[1]
UI = (BASE/'aeroscope/ui.py').read_text()
PIP = (BASE/'aeroscope/mini_map.py').read_text()
MON = (BASE/'aeroscope/monitor_ui.py').read_text()
PREF = (BASE/'aeroscope/preferences.py').read_text()


def test_all_components_parse():
    for source in (UI,PIP,MON,PREF):
        ast.parse(source)


def test_geolocate_again_uses_last_system_fix_and_animated_map():
    assert 'self._last_system_fix = None' in UI
    assert 'if self._last_system_fix is not None and not force:' in UI
    assert 'self._last_system_fix = (lat, lon)' in UI
    assert 'if self._last_location_fix is not None and not force:' in UI
    assert 'Last approximate IP location' in UI
    assert 'animated=True' in UI
    assert 'self.map.go_to_full_with_duration(lat, lon, zoom, 750)' in UI
    assert 'self.map.go_to_full_with_duration(lat, lon, self.viewport.get_zoom_level(), 750)' in PIP
    assert 'self._finish_camera_transition' in PIP
    assert 'self._set_my_position(lat, lon)' in UI
    assert 'pip.recenter_location(lat, lon)' in UI


def test_main_map_controls_and_no_double_zoom_controls():
    assert 'self.simple_map.set_show_zoom_buttons(False)' in UI
    assert 'self.map_overlay.add_overlay(map_controls)' in UI
    assert "geo = icon_button('find-location-symbolic'" in UI
    assert 'self.zoom(d)' in UI


def test_history_toggle_is_next_to_refresh():
    assert 'self.show_emergency_history = Gtk.ToggleButton()' in MON
    assert 'self.show_emergency_history.set_icon_name' in MON
    assert 'world_cmd.append(self.refresh_em_btn)' in MON
    assert 'world_cmd.append(self.show_emergency_history)' in MON
    assert MON.index('world_cmd.append(self.refresh_em_btn)') < MON.index('world_cmd.append(self.show_emergency_history)') < MON.index('world.append(world_cmd)')
    assert 'self.show_emergency_history.get_active()' in MON


def test_sweep_menu_order_and_dependency():
    tower="append_menu_action(visual_menu, _('Control tower mode'), 'app.toggle-tower')"
    sweep="append_menu_action(visual_menu, _('Rotating sweep'), 'app.toggle-sweep')"
    clock="visual_menu.append(_('Aircraft clock'), 'app.toggle-clock')"
    assert UI.index(tower) < UI.index(sweep) < UI.index(clock)
    assert "sweep_action.set_enabled(bool(initial_settings['tower']))" in UI
    assert 'sweep.set_enabled(bool(enabled))' in UI
    assert "self.visual_rows['tower_sweep'].set_sensitive(bool(enabled))" in PREF
    assert "self.visual_rows['tower_sweep'].set_sensitive(bool(settings['tower']))" in PREF
