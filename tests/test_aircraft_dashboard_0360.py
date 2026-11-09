"""Regression tests for compact aircraft dashboard and defensive routeset lookup.

GTK graphics are exercised by manual UI testing; these logic tests run headless.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeroscope.dashboard_layout import normalize, widget_key
from aeroscope import data

ROOT = Path(__file__).resolve().parents[1]


def _function_from_source(relative, name, cls=None):
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'))
    body = tree.body
    if cls:
        body = next(node.body for node in body if isinstance(node, ast.ClassDef) and node.name == cls)
    func = next(node for node in body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    env = {}
    exec(compile(ast.Module(body=[func], type_ignores=[]), str(ROOT / relative), 'exec'), env)
    return env[name]


def test_aircraft_dashboard_codes_safe_and_roundtrip():
    assert widget_key('aircraft', 'e498c8') == 'aircraft:E498C8'
    with pytest.raises(ValueError):
        widget_key('aircraft', '../fake')
    with pytest.raises(ValueError):
        widget_key('aircraft', 'PSBVP')
    data = {'fullscreen': True, 'widgets': [
        {'kind': 'aircraft', 'code': 'e498c8', 'collapsed': True, 'x': .4, 'y': .8},
        {'kind': 'aircraft', 'code': 'E498C8', 'collapsed': False, 'x': .1, 'y': .1},
    ]}
    norm = normalize(data)
    assert norm['widgets'] == [{'kind': 'aircraft', 'code': 'E498C8', 'collapsed': True,
                                'x': .4, 'y': .8}]


def test_aircraft_header_has_center_follow_next_to_close_and_compact_mode():
    text = (ROOT / 'aeroscope/aircraft_widget.py').read_text()
    assert text.index('header.append(self.collapse_button)') < text.index('header.append(self.center_button)')
    assert text.index('header.append(self.center_button)') < text.index('header.append(self.follow_button)')
    assert text.index('header.append(self.follow_button)') < text.index('header.append(close)')
    assert "self.center_button.connect('clicked', self._center_on_map)" in text
    assert "self.follow_button.connect('clicked', self._toggle_follow)" in text
    assert "self.follow_button.set_icon_name('media-playback-pause-symbolic'" in text
    assert 'self.center_button.set_sensitive(live_position)' in text
    assert 'self.follow_button.set_sensitive(live_position)' in text
    assert "self.controller.toggle_aircraft_follow(self.code)" in text
    assert "self.controller.center_aircraft(self.code)" in text
    assert 'self.expanded_revealer.set_reveal_child(not self.collapsed)' in text
    assert 'fetch_history' not in text  # Avoid retrieving archived flight history for a card.
    ast.parse(text)


def test_center_aircraft_uses_existing_smooth_navigation_without_new_follow_mode():
    center = _function_from_source('aeroscope/dashboard.py', 'center_aircraft', 'DashboardController')
    calls = []
    radar = SimpleNamespace(records={'e498c8': object()},
                            _center_aircraft_from_menu=lambda code: calls.append(('center', code)))
    dashboard = SimpleNamespace(radar=radar, update_aircraft_actions=lambda: calls.append(('sync',)))
    assert center(dashboard, 'E498C8') is True
    assert calls == [('center', 'e498c8'), ('sync',)]
    assert center(dashboard, 'ffffff') is False
    assert calls == [('center', 'e498c8'), ('sync',)]


def test_follow_button_toggles_existing_follow_state_and_syncs_sidebar():
    toggle = _function_from_source('aeroscope/dashboard.py', 'toggle_aircraft_follow', 'DashboardController')
    events = []
    radar = SimpleNamespace(records={'e498c8': object()}, selected_hex=None, follow=False)
    def select_plane(hexid):
        events.append(('select', hexid))
        radar.selected_hex = hexid
    radar.select_plane = select_plane
    radar._render_details = lambda: events.append(('render', radar.follow))
    dashboard = SimpleNamespace(radar=radar, update_aircraft_actions=lambda: events.append(('sync',)))
    assert toggle(dashboard, 'E498C8') is True
    assert radar.follow is True
    assert events == [('select', 'e498c8'), ('render', True), ('sync',)]
    assert toggle(dashboard, 'E498C8') is True
    assert radar.follow is False
    assert events[-2:] == [('render', False), ('sync',)]
    assert toggle(dashboard, 'ffffff') is False
    assert events[-2:] == [('render', False), ('sync',)]


class _RouteResponse:
    def __init__(self, body, status=200):
        self.body, self.status = body, status
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, limit=-1):
        return self.body[:limit]


@pytest.mark.parametrize('payload, message', [
    (b'', 'empty response'), (b'   ', 'empty response'),
    (b'<html>blocked</html>', 'invalid data'),
    (b'not-json', 'invalid data'),
    (b' ' * 500_001, 'too large'),
])
def test_routeset_handles_bad_http_body_without_jsondecode_warning(monkeypatch, payload, message):
    monkeypatch.setattr(data, '_', lambda value: value)  # message language-independent
    monkeypatch.setattr(data.urllib.request, 'urlopen',
                        lambda *_args, **_kwargs: _RouteResponse(payload))
    with pytest.raises(RuntimeError, match=message):
        data.fetch_live_route('PSBVP', -19.9, -44.0)


def test_routeset_no_content_returns_none_without_inventing_airport(monkeypatch):
    monkeypatch.setattr(data.urllib.request, 'urlopen',
                        lambda *_args, **_kwargs: _RouteResponse(b'', 204))
    assert data.fetch_live_route('PSBVP', -19.9, -44.0) is None
