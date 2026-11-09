"""Regression coverage for PiP controls and the volatile emergency log."""
from pathlib import Path
from aeroscope.emergency_history import SessionEmergencyHistory, observed_at

ROOT = Path(__file__).resolve().parents[1]
PIP = (ROOT / 'aeroscope/mini_map.py').read_text()
UI = (ROOT / 'aeroscope/ui.py').read_text()
MON = (ROOT / 'aeroscope/monitor_ui.py').read_text()


def event(hexid='e48df5', code='7700'):
    return {'hex': hexid, 'squawk': code, 'flight': 'ARCANJO9',
            'registration': 'PT-MUJ', 'description': 'Emergência geral'}


def test_emergency_observed_and_closed_only_after_successful_scan():
    h = SessionEmergencyHistory()
    assert h.observe([event()], {}, 1000) == []
    assert h.observe([event()], {}, 1060) == []
    assert len(h.records) == 1
    assert h.records[0]['first_seen'] == 1000
    assert h.records[0]['last_seen'] == 1060
    assert h.observe([], {'7700': 'timeout'}, 1120) == []
    assert h.ended() == []
    closed = h.observe([], {}, 1180)
    assert len(closed) == 1
    assert closed[0]['no_longer_seen'] == 1180
    assert len(h.ended()) == 1
    assert 'UTC' in observed_at(1180)


def test_emergency_reappearance_is_a_new_episode():
    h = SessionEmergencyHistory()
    h.observe([event()], {}, 1000)
    h.observe([], {}, 1100)
    h.observe([event()], {}, 1200)
    assert len(h.records) == 2
    assert len(h.ended()) == 1
    assert h.records[-1]['first_seen'] == 1200
    assert h.records[-1]['no_longer_seen'] is None


def test_partial_code_failure_does_not_end_that_code():
    h = SessionEmergencyHistory()
    h.observe([event(), event('abc123', '7600')], {}, 1000)
    assert len(h.observe([event('abc123', '7600')], {'7700': '429'}, 1300)) == 0
    assert h.records[0]['no_longer_seen'] is None
    assert len(h.observe([], {'7600': 'timeout'}, 1400)) == 1


def test_history_is_in_session_only_and_optional_in_sidebar():
    assert 'self._emergency_history = SessionEmergencyHistory()' in MON
    assert 'self.show_emergency_history = Gtk.ToggleButton()' in MON
    assert "world_cmd.append(self.show_emergency_history)" in MON
    assert "self._emergency_history.observe(self._global_rows" in MON
    assert 'self.show_emergency_history.get_active()' in MON
    assert "row.add_css_class('emergency-history-ended')" in MON


def test_wayland_manual_help_and_x11_checkbox():
    assert 'self.above_check.set_visible(can_toggle)' in PIP
    assert 'self.above_help.set_visible(not can_toggle)' in PIP
    assert "self._above_status == 'requested'" in PIP
    assert 'def _show_above_help(self)' in PIP
    assert 'Alt+F3' in PIP and 'Alt+Space' in PIP
    assert "self._always_top = bool(radar.settings.get('pip_always_on_top', True))" in PIP


def test_follow_and_geolocation_pip_no_second_api():
    assert 'def _follow_visible_aircraft(self):' in PIP
    assert 'self._follow_visible_aircraft()' in PIP
    assert 'selected.marker.get_latitude()' in PIP
    assert 'self._center_without_feedback(lat, lon)' in PIP
    assert "geo = Gtk.Button(icon_name='find-location-symbolic')" in PIP
    assert "geo.connect('clicked', lambda *_: self.radar.locate())" in PIP
    assert 'pip.recenter_location(lat, lon)' in UI
    assert 'fetch_area(' not in PIP


def test_photo_async_and_return_button():
    assert "back = Gtk.Button(icon_name='view-fullscreen-symbolic')" in PIP
    assert "back.connect('clicked', lambda *_: application.show_main_window())" in PIP
    ctx = UI.split('def show_aircraft_context_menu(',1)[1].split('def _toggle_favorite(',1)[0]
    assert "'Buscando fotografia…'" in ctx
    assert 'self._context_photo_waiters.setdefault(hexid, []).append(' in ctx
    assert 'hexid not in self.photo_pending' in ctx
    assert "photo_button.get_child().get_last_child()" in ctx
    assert 'waiters = getattr(self, \'_context_photo_waiters\', {}).pop(hexid, [])' in UI
