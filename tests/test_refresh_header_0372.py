"""0.3.72 regressions: native refresh button and shared provider subtitle."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / 'aeroscope' / 'ui.py').read_text()
WEATHER = (ROOT / 'aeroscope' / 'weather_ui.py').read_text()


def test_refresh_button_matches_native_hamburger_button():
    build = UI.split('    def _build_ui(self):', 1)[1].split('    def ', 1)[0]
    assert "appmenu = Gtk.MenuButton(icon_name='open-menu-symbolic'" in build
    assert "refresh_button = Gtk.MenuButton(" in build
    assert "icon_name='view-refresh-symbolic'" in build
    assert "refresh_button.set_menu_model(refresh_menu)" in build
    assert "header.pack_end(refresh_button)" in build
    assert 'refresh_control' not in build
    assert 'refresh_dropdown' not in build
    assert 'refresh_primary' not in build


def test_manual_noaa_progress_wait_and_completion_use_header_not_toasts():
    section = WEATHER.split('    def _begin_noaa(', 1)[1].split('    def sigmet_at_location(', 1)[0]
    assert 'self.radar.set_weather_status(' in section
    assert 'self.radar.notify(' not in section
    for message in ('Updating {value0}', 'queued; waiting', 'update already in progress',
                    'wait {value1} s', 'update failed', 'partially updated', 'updated.'):
        assert message in section


def _fake_header():
    """Execute production header methods with fake clock/GLib, no GUI required."""
    source = ast.parse(UI)
    radar = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'RadarWindow')
    keep = {'_display_status', 'set_status', 'set_weather_status', '_restore_radar_status'}
    methods = [n for n in radar.body if isinstance(n, ast.FunctionDef) and n.name in keep]
    assert {n.name for n in methods} == keep
    cls_node = ast.ClassDef(name='HeaderOnly', bases=[], keywords=[], body=methods, decorator_list=[])
    mod = ast.fix_missing_locations(ast.Module(body=[cls_node], type_ignores=[]))
    clock = SimpleNamespace(now=50.0)
    scheduled = []
    titles = []
    glib = SimpleNamespace(timeout_add=lambda ms, cb, token: scheduled.append((ms, cb, token)),
                           SOURCE_REMOVE=False)
    namespace = {'time': SimpleNamespace(monotonic=lambda: clock.now), 'GLib': glib,
                 '_': lambda text: text}
    exec(compile(mod, str(ROOT / 'aeroscope' / 'ui.py'), 'exec'), namespace)
    obj = namespace['HeaderOnly']()
    obj.demo = False
    obj._query_anchor = None
    obj.window_title = SimpleNamespace(set_subtitle=titles.append)
    obj._last_radar_status = ('Connecting to API…', False)
    obj._weather_status_until = 0.0
    obj._weather_status_token = 0
    return obj, clock, scheduled, titles


def test_weather_header_restores_latest_radar_status_without_flicker():
    obj, clock, scheduled, titles = _fake_header()
    obj.set_status('12 aircraft visible')
    obj.set_weather_status('NOAA METAR: wait 37 s before refreshing again.')
    obj.set_status('15 aircraft visible')
    assert titles[-1] == 'NOAA METAR: wait 37 s before refreshing again.'
    assert len(scheduled) == 1
    assert scheduled[-1][0] >= 5000
    clock.now += 6
    _, callback, token = scheduled[-1]
    callback(token)
    assert titles[-1] == '15 aircraft visible'


def test_overlapping_weather_messages_restore_only_after_latest_one():
    obj, clock, scheduled, titles = _fake_header()
    obj.set_status('Radar is live')
    obj.set_weather_status('Updating METAR…', hold=30)
    obj.set_weather_status('NOAA METAR: updated.', hold=5)
    before = len(titles)
    old = scheduled[0]
    old[1](old[2])
    assert len(titles) == before
    clock.now += 5.1
    latest = scheduled[1]
    latest[1](latest[2])
    assert titles[-1] == 'Radar is live'


def test_adsb_error_preempts_weather_status():
    obj, _clock, scheduled, titles = _fake_header()
    obj.set_weather_status('Updating SIGMET…', hold=30)
    obj.set_status('ADSB.lol: HTTP 429', error=True)
    assert titles[-1] == '⚠ ADSB.lol: HTTP 429'
    old = scheduled[0]
    old[1](old[2])
    assert titles[-1] == '⚠ ADSB.lol: HTTP 429'


def test_noaa_subtitle_does_not_claim_adsb_250_nm_coverage():
    obj, _clock, _scheduled, titles = _fake_header()
    obj._query_anchor = (-20.0, -44.0)
    obj.set_weather_status('Updating METAR…')
    assert titles[-1] == 'Updating METAR…'
    obj.set_status('Radar ready')
    assert titles[-1] == 'Updating METAR…'
