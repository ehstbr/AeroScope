"""Dashboard 0.3.56: persistence, safe input, and north-up gesture guard."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

from aeroscope.dashboard_layout import normalize, load_layout, save_layout, widget_key
from aeroscope.map_orientation import lock_north_up

ROOT = Path(__file__).resolve().parents[1] / 'aeroscope'


def test_dashboard_layout_roundtrip_and_fullscreen(tmp_path):
    dest = tmp_path / 'nested' / 'dashboard.json'
    expected = {'version': 1, 'fullscreen': True, 'widgets': [
        {'kind': 'airport', 'code': 'PLU', 'x': .24, 'y': .34, 'collapsed': False},
        {'kind': 'station', 'code': 'SBBH', 'x': .62, 'y': .65, 'collapsed': True},
    ]}
    save_layout(expected, dest)
    assert load_layout(dest) == expected
    assert json.loads(dest.read_text('utf-8'))['fullscreen'] is True


def test_dashboard_layout_sanitizes_duplicates_and_corrupt_fields(tmp_path):
    corrupted = {'fullscreen': 'true', 'widgets': [
        {'kind': 'airport', 'code': 'PLU', 'x': 'nan', 'y': 3, 'collapsed': 'yes'},
        {'kind': 'airport', 'code': 'PLU', 'x': .2},
        {'kind': 'station', 'code': 'SBZZ', 'x': -1, 'y': .3, 'collapsed': True},
        {'kind': 'plane', 'code': 'ABCDEF', 'x': .3},
        {},
    ]}
    value = normalize(corrupted)
    assert value['fullscreen'] is False
    assert len(value['widgets']) == 2
    assert value['widgets'][0]['x'] == .04
    assert value['widgets'][0]['y'] == 1.0
    assert value['widgets'][0]['collapsed'] is False
    assert value['widgets'][1]['collapsed'] is True
    (tmp_path / 'dashboard.json').write_text('{bad json')
    assert load_layout(tmp_path / 'dashboard.json')['widgets'] == []


def test_codes_cannot_inject_paths_or_markup():
    import pytest
    for kind, code in [('airport', '../x'), ('station', '<abc>'),
                       ('test', 'SBBH'), ('airport', '')]:
        with pytest.raises(ValueError):
            widget_key(kind, code)
    assert widget_key('Station', 'sbbh') == 'station:SBBH'
    with pytest.raises(ValueError):
        widget_key('station', 'SB-0')


def test_rotation_block_only_disables_rotate_controller():
    class FakeRotate:
        def __init__(self):
            self.phase = None
            self.did_reset = False
        def set_propagation_phase(self, value):
            self.phase = value
        def reset(self):
            self.did_reset = True
    class FakeZoom:
        def __init__(self):
            self.phase = 'ZOOM'
    class FakeViewport:
        def __init__(self):
            self.rotation = 2.5
        def set_rotation(self, degrees):
            self.rotation = degrees
        def get_rotation(self):
            return self.rotation
        def connect(self, name, cb):
            assert name == 'notify::rotation'
            self.cb = cb
    rot, zoom = FakeRotate(), FakeZoom()
    model = SimpleNamespace(get_n_items=lambda: 2,
                            get_item=lambda index: [rot, zoom][index])
    vp = FakeViewport()
    class FakeMap:
        def observe_controllers(self):
            return model
    gtk = SimpleNamespace(GestureRotate=FakeRotate,
                          PropagationPhase=SimpleNamespace(NONE='OFF'))
    assert lock_north_up(vp, FakeMap(), gtk) == 1
    assert rot.phase == 'OFF' and rot.did_reset
    assert zoom.phase == 'ZOOM'
    assert vp.get_rotation() == 0.0
    vp.rotation = .5
    vp.cb(vp)
    assert vp.get_rotation() == 0.0


def test_dashboard_context_actions_and_shortcut_present():
    code = (ROOT / 'ui.py').read_text()
    mini = (ROOT / 'mini_map.py').read_text()
    weather = (ROOT / 'weather_ui.py').read_text()
    assert "self.set_accels_for_action('app.toggle-dashboard', ['F11'])" in code
    assert "self.main_sidebar.set_visible(not enabled)" in code
    assert "self.main_header.set_visible(not enabled)" in code
    assert "self.dashboard.has('airport', iata)" in code
    assert "self.dashboard.has('station', metar.station)" in code
    assert 'lock_north_up(self.viewport, self.map, Gtk)' in code
    assert 'lock_north_up(self.viewport, self.map, Gtk)' in mini
    assert 'dashboard.station_codes()' in weather
    assert 'code not in self.notification_metar_codes()' in weather
    for module in (ROOT / 'dashboard.py', ROOT / 'floating_widget.py'):
        ast.parse(module.read_text())
