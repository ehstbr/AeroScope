"""Ensure keyboard handler executes with the GDK4 modifier names."""
import ast
from pathlib import Path
from types import SimpleNamespace

from aeroscope.keyboard_shortcuts import keyboard_command

ROOT = Path(__file__).resolve().parents[1]


def _handler_in_gdk4_namespace():
    ui = (ROOT / 'aeroscope/ui.py').read_text()
    # Compile just the method to exercise the real handler without importing
    # the complete GTK window or requiring a running display.
    tree = ast.parse(ui)
    method = next(node for cls in ast.walk(tree) if isinstance(cls, ast.ClassDef)
                  for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == '_keyboard_shortcut_pressed')
    isolated = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(isolated)
    gdk4_modifiers = SimpleNamespace(CONTROL_MASK=4, ALT_MASK=8, SUPER_MASK=1 << 26)
    # Deliberately no MOD1_MASK in this GDK4 stand-in.
    namespace = {
        'Gdk': SimpleNamespace(ModifierType=gdk4_modifiers,
                               keyval_name=lambda keyval: keyval),
        'Gtk': SimpleNamespace(Editable=type('Editable', (), {}),
                               TextView=type('TextView', (), {})),
        'keyboard_command': keyboard_command,
    }
    exec(compile(isolated, str(ROOT / 'aeroscope/ui.py'), 'exec'), namespace)
    return namespace['_keyboard_shortcut_pressed']


class _Window:
    def __init__(self):
        self.actions = []

    def get_focus(self):
        return None

    def zoom(self, delta):
        self.actions.append(('zoom', delta))

    def locate(self):
        self.actions.append(('locate',))


def test_handler_works_without_obsolete_gdk3_modifier():
    handler = _handler_in_gdk4_namespace()
    win = _Window()
    assert handler(win, None, 'plus', 0, 0) is False
    assert handler(win, None, 'plus', 0, 8) is True
    assert win.actions == [('zoom', 1)]
    assert handler(win, None, 'minus', 0, 8) is True
    assert win.actions[-1] == ('zoom', -1)
    assert handler(win, None, 'period', 0, 8) is True
    assert win.actions[-1] == ('locate',)
    assert handler(win, None, 'plus', 0, 4) is False
    assert handler(win, None, 'plus', 0, (4 | 8)) is False
    assert handler(win, None, 'plus', 0, (8 | 1 << 26)) is False
    assert len(win.actions) == 3


def test_no_obsolete_gdk3_modifier_constants_remain():
    for path in (ROOT / 'aeroscope').rglob('*.py'):
        text = path.read_text()
        assert 'ModifierType.MOD1_MASK' not in text, path
        assert 'ModifierType.MOD2_MASK' not in text, path


def test_handler_preserves_select_copy_and_paste_with_search_focus():
    handler = _handler_in_gdk4_namespace()
    win = _Window()
    editable = handler.__globals__['Gtk'].Editable()
    win.get_focus = lambda: editable
    for key in ('a', 'c', 'v', 'A', 'C', 'V'):
        assert handler(win, None, key, 0, 4) is False
        assert handler(win, None, key, 0, 12) is False
    assert handler(win, None, 'plus', 0, 8) is True
    assert win.actions == [('zoom', 1)]
