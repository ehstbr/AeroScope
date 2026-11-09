"""Regression tests for GTK4 floating dashboard entry and exit fades."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from aeroscope.dashboard_fade import (FADE_IN_MS, FADE_OUT_MS,
                                      opacity_at, fade_widget)

ROOT = Path(__file__).resolve().parents[1]


class FakeCard:
    def __init__(self):
        self.opacity = 1.0
        self.tick = None
        self.parent = None
        self.target = True
        self.positions = (185, 110)

    def set_opacity(self, opacity):
        self.opacity = opacity

    def add_tick_callback(self, callback):
        self.tick = callback
        return 101

    def set_can_target(self, allowed):
        self.target = allowed

    def get_parent(self):
        return self.parent


class FakeClock:
    def __init__(self, microseconds):
        self.time = microseconds

    def get_frame_time(self):
        return self.time


def tick_at(card, at):
    return card.tick(card, FakeClock(at))


def test_opacity_curve_is_bounded_and_smooth():
    assert (FADE_IN_MS, FADE_OUT_MS) == (150, 130)
    for appearing in (True, False):
        a = [opacity_at(i, 150, appearing=appearing)
             for i in (-100000, 0, 37500, 75000, 112500, 150000, 300000)]
        assert all(0 <= value <= 1 for value in a)
        assert a[0] == a[1]
        assert a[3] == .5
        assert a[-1] == a[-2]
        assert a == sorted(a, reverse=not appearing)


def test_fade_in_does_not_move_card():
    card = FakeCard()
    done = []
    assert fade_widget(card, appearing=True, on_finished=lambda: done.append(1)) == 101
    assert card.opacity == 0
    assert tick_at(card, 1_000_000) is True
    assert tick_at(card, 1_075_000) is True
    assert 0 < card.opacity < 1
    assert tick_at(card, 1_150_000) is False
    assert card.opacity == 1
    assert done == [1]
    assert card.positions == (185, 110)


def test_fade_out_defers_remove_until_last_frame():
    card = FakeCard()
    done = []
    fade_widget(card, appearing=False, on_finished=lambda: done.append('removed'))
    assert card.opacity == 1
    assert tick_at(card, 9_000_000) is True
    assert done == []
    assert tick_at(card, 9_065_000) is True
    assert card.opacity == .5
    assert done == []
    assert tick_at(card, 9_130_000) is False
    assert card.opacity == 0
    assert done == ['removed']


def test_disabled_animations_are_immediate_without_scheduling_tick():
    for appearing in (True, False):
        card = FakeCard()
        removed = []
        assert fade_widget(card, appearing=appearing, enabled=False,
                           on_finished=lambda: removed.append('done')) is None
        assert card.tick is None
        assert card.opacity == (1 if appearing else 0)
        assert removed == ['done']


def extract_method(name):
    module = ast.parse((ROOT / 'aeroscope' / 'dashboard.py').read_text())
    klass = next(node for node in module.body
                 if isinstance(node, ast.ClassDef) and node.name == 'DashboardController')
    method = next(node for node in klass.body
                  if isinstance(node, ast.FunctionDef) and node.name == name)
    return method


def test_add_only_animates_new_widgets_not_restoration():
    source = (ROOT / 'aeroscope' / 'dashboard.py').read_text()
    assert 'self._create(entry, animate=True)' in source
    assert 'self._create(entry)\n        self.relayout()' in source
    creation = ast.unparse(extract_method('_create'))
    assert 'fade_widget(card, appearing=True' in creation
    assert 'self.overlay.add_overlay(card)' in creation
    assert creation.index('self.overlay.add_overlay(card)') < creation.index('fade_widget(')


def test_remove_updates_registry_once_and_unparents_only_after_fade():
    fn = extract_method('remove')
    idles = []
    ns = {'widget_key': lambda kind, code: f'{kind}:{code}', 'fade_widget': fade_widget,
          'GLib': SimpleNamespace(idle_add=lambda callback, card: idles.append((callback, card)))}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'dashboard.py', 'exec'), ns)
    card = FakeCard()
    removed = []
    overlay = SimpleNamespace(remove_overlay=lambda card: removed.append(card))
    card.parent = overlay
    saved = []
    notified = []
    manager = SimpleNamespace(
        cards={'station:SBXX': card}, overlay=overlay,
        layout={'widgets': [{'kind': 'station', 'code': 'SBXX'}]},
        _persist=lambda: saved.append(1),
        radar=SimpleNamespace(weather=SimpleNamespace(favorites_changed=lambda: notified.append(1))),
        _animations_enabled=lambda: True,
        _finish_card_removal=lambda target: (removed.append(target) if target.get_parent() is overlay else None),
    )
    ns['remove'](manager, 'station', 'SBXX')
    assert manager.cards == {}
    assert manager.layout['widgets'] == []
    assert saved == [1]
    assert notified == [1]
    assert card.target is False
    assert removed == []
    ns['remove'](manager, 'station', 'SBXX')
    assert saved == [1], 'repeat click must not close again'
    tick_at(card, 2_000_000)
    assert removed == []
    tick_at(card, 2_130_000)
    assert removed == [], 'unparenting must be deferred out of the tick callback'
    assert len(idles) == 1
    idles.pop()[0](card)
    assert removed == [card]
