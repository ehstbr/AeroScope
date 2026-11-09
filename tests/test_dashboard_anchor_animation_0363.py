"""Regression: folding/unfolding a card must never move its top-left anchor."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from aeroscope.dashboard_layout import (anchor_fraction, anchor_pixel,
                                       load_layout, save_layout)

ROOT = Path(__file__).resolve().parents[1] / 'aeroscope'


def _extract(module, cls_name, method_name, imports=None):
    source = (ROOT / module).read_text(encoding='utf-8')
    tree = ast.parse(source)
    cls = next(item for item in tree.body
               if isinstance(item, ast.ClassDef) and item.name == cls_name)
    func = next(item for item in cls.body
                if isinstance(item, ast.FunctionDef) and item.name == method_name)
    namespace = dict(imports or {})
    exec(compile(ast.Module(body=[func], type_ignores=[]), str(ROOT / module), 'exec'), namespace)
    return namespace[method_name]


class FakeCard:
    _drag_offset = None
    def __init__(self, width=310, height=240):
        self.width, self.height = width, height
        self.x, self.y = 0, 0
    def get_width(self): return self.width
    def get_height(self): return self.height
    def set_margin_start(self, value): self.x = value
    def set_margin_top(self, value): self.y = value
    def get_margin_start(self): return self.x
    def get_margin_top(self): return self.y


class FakeOverlay:
    def __init__(self, width=1200, height=800):
        self.width, self.height = width, height
    def get_width(self): return self.width
    def get_height(self): return self.height


def _fake_dashboard():
    from aeroscope.dashboard_layout import bounded_fraction
    overlay = FakeOverlay()
    card = FakeCard()
    entry = {'kind': 'aircraft', 'code': 'ABCDEF', 'x': 0.2, 'y': 0.6, 'collapsed': False}
    events = []
    manager = SimpleNamespace(overlay=overlay, cards={'aircraft:ABCDEF': card},
                              _entry=lambda item: entry, _persist=lambda: events.append('saved'))
    available = lambda item: (max(0, overlay.width - max(276, item.width)),
                              max(0, overlay.height - max(95, item.height)))
    manager._available = available
    env = dict(GLib=SimpleNamespace(SOURCE_REMOVE=False),
               anchor_fraction=anchor_fraction, anchor_pixel=anchor_pixel,
               bounded_fraction=bounded_fraction)
    return manager, card, entry, events, env


def test_migrated_anchor_keeps_position_after_height_changes(tmp_path):
    manager, card, entry, events, env = _fake_dashboard()
    relayout = _extract('dashboard.py', 'DashboardController', 'relayout', env)
    # Old layout fractions were relative to the free space below/right.
    assert relayout(manager) is False
    assert (card.x, card.y) == (178, 336)  # 1200-310 and 800-240
    assert events == ['saved']
    original = (card.x, card.y)
    # The Gtk.Revealer shrinks the card and its allocation, but NOT its anchor.
    card.height = 110
    relayout(manager)
    assert (card.x, card.y) == original
    card.height = 280
    relayout(manager)
    assert (card.x, card.y) == original
    assert events == ['saved'], 'migration only happens once'
    assert entry['anchor_x'] == anchor_fraction(178, 1200)
    assert entry['anchor_y'] == anchor_fraction(336, 800)
    stored = tmp_path / 'dashboard.json'
    save_layout({'widgets': [entry], 'fullscreen': False}, stored)
    recovered = load_layout(stored)['widgets'][0]
    assert recovered['anchor_x'] == entry['anchor_x']
    assert recovered['anchor_y'] == entry['anchor_y']


def test_drag_updates_stable_anchor_and_screen_resizes():
    manager, card, entry, events, env = _fake_dashboard()
    relayout = _extract('dashboard.py', 'DashboardController', 'relayout', env)
    move = _extract('dashboard.py', 'DashboardController', 'move_pixels', env)
    relayout(manager)
    move(manager, card, 390, 220, persist=True)
    assert (card.x, card.y) == (390, 220)
    assert entry['anchor_x'] == 390 / 1200
    assert entry['anchor_y'] == 220 / 800
    card.height = 90
    relayout(manager)
    assert (card.x, card.y) == (390, 220)
    manager.overlay.width, manager.overlay.height = 1500, 1000
    relayout(manager)
    assert (card.x, card.y) == (488, 275)
    card.height = 500
    relayout(manager)
    assert (card.x, card.y) == (488, 275)


class FakeRevealer:
    def __init__(self): self.value = None
    def set_reveal_child(self, value): self.value = value


class FakeButton:
    def __init__(self): self.icon = self.tip = None
    def set_icon_name(self, icon): self.icon = icon
    def set_tooltip_text(self, text): self.tip = text


class FakeLabel:
    def __init__(self, text=''): self.text, self.visible = text, None
    def set_visible(self, value): self.visible = value
    def get_text(self): return self.text
    def set_label(self, value): self.text = value


def test_aircraft_toggle_uses_animated_revealers_without_relayout():
    fn = _extract('aircraft_widget.py', 'AircraftFloatingWidget', '_toggle_collapsed', {'_': lambda text: text})
    saved = []
    plane = SimpleNamespace(collapsed=False, kind='aircraft', code='ABCDEF',
                            compact_alert=FakeLabel(''), expanded_revealer=FakeRevealer(),
                            compact_revealer=FakeRevealer(), collapse_button=FakeButton(),
                            controller=SimpleNamespace(set_collapsed=lambda *args: saved.append(args),
                                                       relayout=lambda: 1 / 0))
    fn(plane)
    assert plane.collapsed is True
    assert plane.compact_revealer.value is True
    assert plane.expanded_revealer.value is False
    assert saved == [('aircraft', 'ABCDEF', True)]
    fn(plane)
    assert plane.collapsed is False
    assert plane.compact_revealer.value is False
    assert plane.expanded_revealer.value is True


def test_weather_toggle_uses_revealer_without_relayout():
    fn = _extract('floating_widget.py', 'WeatherFloatingWidget', '_toggle_collapsed', {'_': lambda text: text})
    saved = []
    widget = SimpleNamespace(collapsed=False, kind='station', code='SBBH', name='Pampulha',
                             _flight_category='IFR', expanded_revealer=FakeRevealer(),
                             compact_category=FakeLabel(), title_label=FakeLabel(),
                             set_size_request=lambda *args: None,
                             collapse_button=FakeButton(),
                             controller=SimpleNamespace(set_collapsed=lambda *args: saved.append(args),
                                                        relayout=lambda: 1 / 0))
    fn(widget)
    assert widget.collapsed and widget.expanded_revealer.value is False
    assert widget.compact_category.visible is True
    assert saved == [('station', 'SBBH', True)]
    fn(widget)
    assert not widget.collapsed and widget.expanded_revealer.value is True


def test_native_gtk_revealers_have_small_duration_and_pin_header():
    for fname in ('aircraft_widget.py', 'floating_widget.py'):
        code = (ROOT / fname).read_text()
        assert 'Gtk.Revealer()' in code
        assert 'Gtk.RevealerTransitionType.SLIDE_DOWN' in code
        assert 'set_transition_duration(220)' in code
        assert 'self.controller.relayout()' not in code
        assert 'self.set_valign(Gtk.Align.START)' in code
