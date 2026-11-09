"""Cross-desktop background/PiP regressions without requiring a GUI session."""
from pathlib import Path
from aeroscope.residency import close_behavior, can_monitor_in_background
from aeroscope.settings import DEFAULT
ROOT = Path(__file__).resolve().parents[1]


def test_close_policy_prevents_invisible_unrecoverable_process():
    assert close_behavior(background_enabled=False,pip_enabled=False,
                          indicator_available=True) == 'quit'
    assert close_behavior(background_enabled=True,pip_enabled=False,
                          indicator_available=True) == 'hide'
    assert close_behavior(background_enabled=True,pip_enabled=False,
                          indicator_available=False) == 'confirm'
    assert close_behavior(background_enabled=True,pip_enabled=False,
                          indicator_available=False,warning_accepted=True) == 'hide'
    assert close_behavior(background_enabled=True,pip_enabled=True,
                          indicator_available=False) == 'pip'


def test_monitoring_timers_continue_hidden_and_obey_demo_switch():
    assert can_monitor_in_background(background_active=True,window_mapped=False,demo=False)
    assert can_monitor_in_background(background_active=False,window_mapped=True,demo=False)
    assert not can_monitor_in_background(background_active=False,window_mapped=False,demo=False)
    assert not can_monitor_in_background(background_active=True,window_mapped=False,demo=True)


def test_settings_and_native_menu_items_exist():
    assert DEFAULT['background_on_close'] is True
    assert DEFAULT['close_to_pip'] is False
    src=(ROOT/'aeroscope/ui.py').read_text()
    assert "menu.append_section(_('Monitoring'), monitoring_menu)" in src
    assert "menu.append_section(_('View'), visual_menu)" in src
    assert "menu.append_section(_('Window'), window_menu)" in src
    assert "menu.append_section(_('Application'), application_menu)" in src
    assert "self.connect('close-request', self._on_close_requested)" in src
    assert 'self.hold()' in src
    assert 'self._ensure_background_hold()' in src
    assert 'self._end_background_hold()' in src
    assert 'self.window.hide()' in src
    assert 'self.window._persist_map_view()' in src
    assert 'self.window._refresh_visible_alerts()' in src


def test_reused_map_and_monitoring_without_second_api():
    pip=(ROOT/'aeroscope/mini_map.py').read_text()
    assert "self.simple_map.set_map_source(radar.map_sources[radar.settings['map']])" in pip
    assert 'for hexid, original in self.radar.markers.items():' in pip
    assert 'marker.marker.set_location(original.marker.get_latitude(),' in pip
    assert 'fetch_area(' not in pip and 'fetch_global_emergencies(' not in pip
    monitor=(ROOT/'aeroscope/monitor_ui.py').read_text()
    assert 'can_monitor_in_background(' in monitor


def test_tray_has_context_menu_and_no_gtk3_dependency():
    source=(ROOT/'aeroscope/status_tray.py').read_text()
    assert 'org.kde.StatusNotifierItem' in source
    assert 'com.canonical.dbusmenu' in source
    assert 'Open AeroScope' in source
    assert 'Show mini-map' in source
    assert 'Quit AeroScope' in source
    assert 'from gi.repository import Gio, GLib' in source


def test_clock_contrast_and_preferences():
    ui=(ROOT/'aeroscope/ui.py').read_text()
    segment=ui.split('def _draw_relative_clock',1)[1].split('def _draw_clock_overlay',1)[0]
    assert 'cr.set_line_width(4.0)' in segment
    assert 'cr.set_line_width(1.75)' in segment
    prefs=(ROOT/'aeroscope/preferences.py').read_text()
    assert 'Continue monitoring when window closes' in prefs
    assert 'Show mini-map when closing' in prefs
