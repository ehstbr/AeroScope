"""X11 mini-map placement and multi-monitor source selection regressions."""
from pathlib import Path
from unittest.mock import Mock

from aeroscope.pip_windowing import (bottom_right_position, request_x11_position,
                                     request_window_corner)

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT/'aeroscope'/'ui.py').read_text()
MINI = (ROOT/'aeroscope'/'mini_map.py').read_text()


def test_bottom_right_of_second_monitor_with_margin():
    # Distinct second display starts at x=1920.
    assert bottom_right_position((1920, 0, 2560, 1440), (450, 290)) == (4006, 1126)


def test_negative_origin_monitor_and_margins():
    assert bottom_right_position((-1600, 100, 1600, 900), (450, 290)) == (-474, 686)


def test_workarea_intersection_keeps_panel_clear_and_correct_screen():
    # Panel consumes 48 pixels at the bottom of the secondary screen.
    assert bottom_right_position((1920, 0, 1920, 1080), (450, 290),
                                 workarea=(1920, 0, 1920, 1032)) == (3366, 718)
    # Workarea can be global; use its intersection with the chosen display.
    assert bottom_right_position((1920, 0, 1920, 1080), (450, 290),
                                 workarea=(0, 0, 3840, 1032)) == (3366, 718)


def test_unrelated_workarea_falls_back_to_source_monitor():
    assert bottom_right_position((1920, 0, 1920, 1080), (450, 290),
                                 workarea=(0, 0, 1280, 720)) == (3366, 766)


def test_no_x11_does_not_fake_success():
    assert request_x11_position(0, 4, 4) is False
    assert request_window_corner(Mock(get_surface=lambda: None), Mock()) == 'not-ready'


def test_capture_monitor_before_main_is_hidden():
    main_pip = UI.split('def show_pip(self):', 1)[1].split('def _pip_sync_tick', 1)[0]
    assert main_pip.index('source_monitor = self._pip_source_monitor()') < main_pip.index('self.window.hide()')
    assert main_pip.index('self.pip_window.set_source_monitor(source_monitor)') < main_pip.index('self.pip_window.present()')
    lookup = UI.split('def _pip_source_monitor(self):', 1)[1].split('def show_pip(self):', 1)[0]
    assert 'get_monitor_at_surface(surface)' in lookup
    assert 'self._last_main_monitor = monitor' in lookup


def test_placement_occurs_once_at_open_and_no_extra_adsb_queries():
    assert 'GLib.timeout_add(100, self._place_after_present' in MINI
    assert 'request_window_corner(self, self._placement_monitor, margin=24)' in MINI
    assert 'self._placement_serial' in MINI
    assert '_refresh' not in MINI.split('def _place_after_present(', 1)[1].split('def _on_mapped(', 1)[0]
