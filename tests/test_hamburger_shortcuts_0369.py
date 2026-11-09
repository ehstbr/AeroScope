"""GTK4 hamburger menu shows the shortcuts that really exist, without hijacking Ctrl."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from aeroscope.keyboard_shortcuts import MENU_ACCELERATORS, keyboard_command

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'aeroscope/ui.py').read_text()


def test_menu_accelerators_match_effective_key_commands():
    assert MENU_ACCELERATORS == {
        'app.monitor': '<Alt>b', 'app.global-alerts': '<Alt>e',
        'app.toggle-tower': '<Alt>t', 'app.toggle-sweep': '<Alt>s',
        'app.toggle-weather-metar': '<Alt>m', 'app.toggle-weather-sigmet': '<Alt>a',
        'app.toggle-dashboard': 'F11', 'app.pip': '<Alt>p',
        'app.preferences': '<Alt>comma', 'app.shortcuts': 'F1',
        'app.quit': '<Alt>q',
    }
    expected = {
        'app.monitor': ('b', 'bookmarks'),
        'app.global-alerts': ('e', 'emergencies'),
        'app.toggle-tower': ('t', 'tower'),
        'app.toggle-sweep': ('s', 'sweep'),
        'app.toggle-weather-metar': ('m', 'metar'),
        'app.toggle-weather-sigmet': ('a', 'advisories'),
        'app.pip': ('p', 'pip'),
    }
    for action, (key, command) in expected.items():
        assert keyboard_command(key, alt=True) == command, action
        assert keyboard_command(key, ctrl=True) is None
        assert keyboard_command(key, ctrl=True, alt=True) is None
    for key in ('a', 'c', 'v'):
        assert keyboard_command(key, ctrl=True, editing=True) is None
    for action, accel in (
            ('app.toggle-dashboard', 'F11'), ('app.shortcuts', 'F1'),
            ('app.preferences', '<Alt>comma'), ('app.quit', '<Alt>q')):
        assert f"self.set_accels_for_action('{action}', ['{accel}'])" in SRC


def test_native_menu_item_builder_sets_gtk_accel_attribute_only_when_needed():
    """Execute just the helper AST with GI-free fakes for regression testing."""
    tree = ast.parse(SRC)
    method = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                  and x.name == 'append_menu_action')
    namespace = {'MENU_ACCELERATORS': MENU_ACCELERATORS}
    class Item:
        def __init__(self, label, action):
            self.label = label
            self.action = action
            self.attrs = {}
        def set_attribute_value(self, key, value):
            self.attrs[key] = value
    namespace['Gio'] = SimpleNamespace(MenuItem=SimpleNamespace(new=Item))
    namespace['GLib'] = SimpleNamespace(Variant=SimpleNamespace(new_string=lambda x: x))
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<menu-only>', 'exec'), namespace)
    class Menu:
        def __init__(self):
            self.rows = []
        def append(self, label, action):
            self.rows.append((label, action, {}))
        def append_item(self, item):
            self.rows.append((item.label, item.action, item.attrs))
    menu = Menu()
    namespace['append_menu_action'](menu, 'Control tower', 'app.toggle-tower')
    namespace['append_menu_action'](menu, 'Aircraft clock', 'app.toggle-clock')
    assert menu.rows == [('Control tower', 'app.toggle-tower', {'accel': '<Alt>t'}),
                         ('Aircraft clock', 'app.toggle-clock', {})]


def test_every_menu_shortcut_is_displayed_on_its_real_entry():
    model = ast.parse(SRC)
    build = next(node for node in ast.walk(model) if isinstance(node, ast.FunctionDef)
                 and node.name == '_build_ui')
    found = {}
    for node in ast.walk(build):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != 'append_menu_action' or len(node.args) != 3:
            continue
        if isinstance(node.args[2], ast.Constant):
            found[node.args[2].value] = ast.unparse(node.args[1])
    assert set(found) == set(MENU_ACCELERATORS)
    assert 'Full screen dashboard (F11)' not in SRC
    assert "_('Full screen dashboard')" in found['app.toggle-dashboard']
    # The clock, IP location, marker labels etc. still have no invented shortcuts.
    assert "visual_menu.append(_('Aircraft clock'), 'app.toggle-clock')" in SRC
    assert 'app.toggle-clock' not in MENU_ACCELERATORS
