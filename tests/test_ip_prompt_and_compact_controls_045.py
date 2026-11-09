"""Regression coverage for IP prompt consistency and aircraft inspector compactness."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / 'aeroscope' / 'ui.py').read_text()
DIALOG = (ROOT / 'aeroscope' / 'location_dialog.py').read_text()


def test_ip_location_dialog_is_shared_by_pip_and_main():
    ast.parse(UI)
    ast.parse(DIALOG)
    assert 'def _location_dialog_parent(self):' in UI
    assert 'return pip' in UI
    assert 'dialog = IpLocationDialog(' in UI
    assert UI.count('dialog = IpLocationDialog(') == 2
    assert 'self._location_dialog_parent()' in UI
    assert "on_response=self._ip_suggestion_answer" in UI
    assert "on_response=self._ip_permission_answer" in UI


def test_vertical_actions_stay_in_same_order_in_both_windows():
    assert 'choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL' in DIALOG
    assert "('ip', _('Locate using IP'), True)" in UI
    assert "('never', _('Do not suggest again'), False)" in UI
    assert "('later', _('Not now'), False)" in UI
    assert UI.index("('ip', _('Locate using IP'), True)") < UI.index("('never', _('Do not suggest again'), False)")
    assert UI.index("('never', _('Do not suggest again'), False)") < UI.index("('later', _('Not now'), False)")
    assert 'self._callback(self, response)' in DIALOG
    assert "self._answered = True" in DIALOG
    assert "close_response='later'" in UI


def test_aircraft_actions_are_compact_icons_in_header():
    detail = UI.split('    def _render_details(self):', 1)[1].split('    def show_aircraft_context_menu(', 1)[0]
    assert "self.follow_btn = Gtk.ToggleButton(" in detail
    assert "center = icon_button('find-location-symbolic'" in detail
    assert "star = icon_button('starred-symbolic'" in detail
    assert 'header.append(self.follow_btn)' in detail
    assert 'header.append(center)' in detail
    assert 'header.append(star)' in detail
    assert "Gtk.Button(label='Acompanhar')" not in detail
    assert "Gtk.Button(label='Centralizar')" not in detail
    assert 'self.detail_box.append(controls)' not in detail


def test_follow_toggle_still_updates_the_tracking_state():
    handler = UI.split('    def _follow_changed(self, button):', 1)[1].split('    def _draw_trail(', 1)[0]
    assert 'self.follow = button.get_active()' in handler
    assert "button.set_icon_name('media-playback-pause-symbolic'" in handler
    assert 'button.set_tooltip_text(' in handler
