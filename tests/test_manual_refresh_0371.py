"""Independent NOAA selections and native single-button menu (headless)."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeroscope.refresh_selection import refresh_targets
from aeroscope.noaa_schedule import merge_weather_products

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('choice,metar,sigmet,aircraft,weather', [
    ('all', False, False, True, ()),
    ('all', True, False, True, ('metar',)),
    ('all', False, True, True, ('sigmet',)),
    ('all', True, True, True, ('metar', 'sigmet')),
    ('aircraft', True, True, True, ()),
    ('metar', False, False, False, ('metar',)),
    ('sigmet', False, False, False, ('sigmet',)),
])
def test_refresh_menu_dispatch(choice, metar, sigmet, aircraft, weather):
    assert refresh_targets(choice, metar_enabled=metar, sigmet_enabled=sigmet) == (aircraft, weather)


def test_unknown_refresh_option_does_not_issue_any_request():
    with pytest.raises(ValueError):
        refresh_targets('everything-on-earth', metar_enabled=True, sigmet_enabled=True)


def test_selective_noaa_merge_does_not_erase_other_product():
    original = (['old-metar'], ['old-sigmet'])
    assert merge_weather_products(original, (['new-metar'], []), {},
                                  metar=True, sigmet=False) == (['new-metar'], ['old-sigmet'])
    assert merge_weather_products(original, ([], ['new-sigmet']), {},
                                  metar=False, sigmet=True) == (['old-metar'], ['new-sigmet'])


def test_noaa_partial_errors_preserve_prior_valid_data():
    original = (['old-metar'], ['old-sigmet'])
    assert merge_weather_products(original, ([], ['fresh-sigmet']), {'metar': 'offline'},
                                  metar=True, sigmet=True) == (['old-metar'], ['fresh-sigmet'])
    assert merge_weather_products(original, ([], []), {},
                                  metar=True, sigmet=False) == ([], ['old-sigmet'])
    assert merge_weather_products(None, (['first'], []), {},
                                  metar=True, sigmet=False) == (['first'], [])


def test_refresh_menu_is_native_and_contains_all_four_choices():
    ui = (ROOT / 'aeroscope' / 'ui.py').read_text()
    assert "refresh_button = Gtk.MenuButton(" in ui
    assert "refresh_button.set_menu_model(refresh_menu)" in ui
    assert "header.pack_end(refresh_button)" in ui
    assert "refresh_control.add_css_class('linked')" not in ui
    for choice in ('all', 'aircraft', 'metar', 'sigmet'):
        assert "'win.refresh-' + option" in ui
        assert f"'refresh-{choice}'" not in ui  # generated in one loop
    assert "self.weather.refresh_now(weather_products)" in ui


@pytest.fixture
def weather_manager(monkeypatch):
    """Load the unmodified WeatherManager class with tiny GI stubs; no display."""
    gi = types.ModuleType('gi')
    repo = types.ModuleType('gi.repository')
    glib = SimpleNamespace(
        SOURCE_CONTINUE=True, SOURCE_REMOVE=False,
        timeout_add_seconds=lambda *_args: 1, idle_add=lambda *_args: 1,
        source_remove=lambda *_args: None,
    )
    for key in ('Gdk', 'Gtk', 'Shumate'):
        setattr(repo, key, SimpleNamespace())
    repo.GLib = glib
    monkeypatch.setitem(sys.modules, 'gi', gi)
    monkeypatch.setitem(sys.modules, 'gi.repository', repo)
    file = ROOT / 'aeroscope' / 'weather_ui.py'
    spec = importlib.util.spec_from_file_location('aeroscope._manual_weather_test', file)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    # Geometry correctness is covered by separate SIGMET geometry tests.
    monkeypatch.setattr(module, 'prepare_sigmets', lambda *_a, **_kw: ())

    messages, requests = [], []
    viewport = SimpleNamespace(get_latitude=lambda: -20.1, get_longitude=lambda: -44.9)
    radar = SimpleNamespace(
        demo=False,
        settings={'weather_metar': True, 'weather_sigmet': True, 'monitor_metar_favorites': False},
        selected_airport=None,
        selected_weather_station=None,
        dashboard=None,
        get_application=lambda: SimpleNamespace(pip_window=None),
        set_weather_status=lambda message, **_kw: messages.append(message),
        _async=lambda job, done: requests.append((job, done)),
        _rebuild_airports=lambda: None,
        _render_details=lambda: None,
    )
    manager = module.WeatherManager(radar)
    manager._visible_viewport = lambda: viewport
    manager._queue_sigmet_targets = lambda: None
    manager._refresh_known_airport_metars = lambda _center, force=False: None
    manager.refresh_favorite_metars = lambda force=False: None
    manager._notify_favorites_panel = lambda: None
    return manager, module, requests, messages


def test_manual_metar_only_preserves_sigmet_and_does_not_call_adsb(weather_manager, monkeypatch):
    manager, module, requests, messages = weather_manager
    manager.noaa = (['cached-metar'], ['cached-sigmet'])
    manager._next_noaa['sigmet'] = float('inf')
    manager._last_noaa_center['sigmet'] = (-20.1, -44.9)
    network = []
    def fetch(lat, lon, *, metar, sigmet):
        network.append((metar, sigmet))
        return (['fresh-metar'], [], {})
    monkeypatch.setattr(module, 'fetch_noaa_with_errors', fetch)
    assert manager.refresh_now(('metar',))
    assert len(requests) == 1
    job, done = requests.pop()
    done(job(), None)
    assert network == [(True, False)]
    assert manager.noaa == (['fresh-metar'], ['cached-sigmet'])
    assert manager._next_noaa['sigmet'] == float('inf')
    assert not requests


def test_manual_sigmet_respects_minimum_gap_without_blocking_metar(weather_manager):
    manager, _module, requests, messages = weather_manager
    manager._last_noaa_request['sigmet'] = __import__('time').monotonic()
    assert not manager.refresh_now(('sigmet',))
    assert len(requests) == 0
    assert any('NOAA' in message for message in messages)
    assert manager.refresh_now(('metar',))
    assert len(requests) == 1


def test_queued_refresh_only_starts_missing_product(weather_manager, monkeypatch):
    manager, module, requests, messages = weather_manager
    manager._next_noaa.update(metar=float('inf'), sigmet=float('inf'))
    manager._last_noaa_center.update(metar=(-20.1, -44.9), sigmet=(-20.1, -44.9))
    monkeypatch.setattr(module, 'fetch_noaa_with_errors', lambda _x, _y, *, metar, sigmet: (
        ['metar'] if metar else [], ['sigmet'] if sigmet else [], {}))
    assert manager.refresh_now(('metar',))
    assert manager.refresh_now(('sigmet',))  # queued while METAR request is running
    assert manager._manual_noaa_pending == {'sigmet'}
    job, done = requests.pop(0)
    done(job(), None)
    assert len(requests) == 1
    job, done = requests.pop(0)
    done(job(), None)
    assert manager.noaa == (['metar'], ['sigmet'])
    assert not manager._manual_noaa_pending


def test_selective_region_updates_do_not_hide_stale_other_product(weather_manager, monkeypatch):
    manager, _module, requests, messages = weather_manager
    manager._next_noaa['sigmet'] = float('inf')
    manager._last_noaa_center['sigmet'] = (-16.0, -40.0)  # far outside current region
    manager._next_noaa['metar'] = float('inf')
    manager._last_noaa_center['metar'] = (-20.1, -44.9)
    manager._last_noaa_started['sigmet'] = __import__('time').monotonic() - 30
    manager.tick()
    assert requests
    assert manager._noaa_inflight == {'sigmet'}
