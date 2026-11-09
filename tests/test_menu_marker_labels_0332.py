"""Regression coverage for the hamburger radio submenu and preferences sync."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / 'aeroscope' / 'ui.py').read_text()
PREFS = (ROOT / 'aeroscope' / 'preferences.py').read_text()


def test_sources_parse():
    ast.parse(UI)
    ast.parse(PREFS)


def test_visual_submenu_has_all_three_modes():
    assert "visual_menu.append_submenu(_('Aircraft identification'), marker_menu)" in UI
    assert "(_('Disabled'), 'off')" in UI
    assert "(_('Registration (ICAO24 if unavailable)'), 'registration')" in UI
    assert "(_('ICAO24 only'), 'icao')" in UI
    assert "option.set_action_and_target_value(" in UI
    assert "'app.marker-label', GLib.Variant.new_string(mode)" in UI
    assert "'marker-label', GLib.VariantType.new('s')" in UI
    assert "marker_label_action.connect('change-state', self._marker_label_changed)" in UI


def test_menu_and_preferences_share_one_setting():
    assert "self.window._change_setting('marker_label', mode)" in UI
    assert "self.get_application().sync_visual_action(key, value)" in UI
    assert "if key == 'marker_label':" in UI
    assert "prefs.sync_visual_setting(key, value)" in UI
    assert "self.marker_label_row.set_selected(index)" in PREFS
    assert "visual.add(self.marker_label_row)" in PREFS
    assert "marker.set_label_mode(value)" in UI
    assert "pip.sync_aircraft()" in UI


def test_original_menu_order_preserved():
    tower = "append_menu_action(visual_menu, _('Control tower mode'), 'app.toggle-tower')"
    sweep = "append_menu_action(visual_menu, _('Rotating sweep'), 'app.toggle-sweep')"
    clock = "visual_menu.append(_('Aircraft clock'), 'app.toggle-clock')"
    label = "visual_menu.append_submenu(_('Aircraft identification'), marker_menu)"
    assert UI.index(tower) < UI.index(sweep) < UI.index(clock) < UI.index(label)
