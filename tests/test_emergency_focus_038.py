"""Regression tests for keeping Emergências active during global aircraft focus."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / 'aeroscope' / 'ui.py').read_text()
MON = (ROOT / 'aeroscope' / 'monitor_ui.py').read_text()


def method(src, name):
    return src.split('    def ' + name + '(', 1)[1].split('\n    def ', 1)[0]


def test_emergency_focus_does_not_switch_sidebar():
    body = method(MON, '_show_aircraft')
    assert 'self.radar.focus_global_aircraft(aircraft)' in body
    assert "set_visible_child_name('visible')" not in body
    assert 'self.radar.move_to(' not in body


def test_global_plane_selected_and_details_without_regional_result():
    body = method(UI, 'focus_global_aircraft')
    assert 'self.selected_hex = plane.hex' in body
    assert 'self._render_details()' in body
    assert 'self._sync_global_selection_marker()' in body
    assert 'self._selected_aircraft()' in method(UI, '_render_details')
    assert 'self._global_selected_aircraft' in method(UI, '_selected_aircraft')


def test_monitored_fix_does_not_pollute_visible_aircraft():
    body = method(UI, '_sync_global_selection_marker')
    assert 'self.marker_layer.add_marker(marker.marker)' in body
    assert 'self.records[' not in body
    assert 'plane.hex in self.markers' in body
    assert 'self._sync_global_selection_marker()' in method(UI, '_apply_planes')


def test_selected_global_marker_removed_when_selection_cleared():
    assert 'self._clear_global_selection()' in method(UI, '_clear_selected')
    assert 'self._clear_global_selection()' in method(UI, 'move_to')
    assert 'self._clear_global_selection()' in method(UI, 'select_plane')


def test_switching_to_airport_or_archive_clears_global_marker():
    assert 'self._clear_global_selection()' in method(UI, 'select_airport')
    assert 'self._clear_global_selection()' in method(UI, '_activate_historical_flight')
