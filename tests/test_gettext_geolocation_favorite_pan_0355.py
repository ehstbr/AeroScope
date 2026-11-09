"""Prevent gettext shadowing in GTK callbacks and regressions in favorite map navigation."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'aeroscope'


def _class_method(path: Path, class_name: str, method: str):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == class_name)
    return next(node for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name == method)


def _gettext_and_local_binding(node):
    # Inspect the direct function body, never child lambda/def scopes.
    class Check(ast.NodeVisitor):
        def __init__(self):
            self.gettext = False
            self.bindings = set()

        def visit_FunctionDef(self, subnode):
            return

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_Lambda = visit_FunctionDef

        def visit_Name(self, subnode):
            if subnode.id == '_' and isinstance(subnode.ctx, (ast.Store, ast.Del)):
                self.bindings.add('_')

        def visit_Call(self, subnode):
            if isinstance(subnode.func, ast.Name) and subnode.func.id == '_':
                self.gettext = True
            self.generic_visit(subnode)

    result = Check()
    if isinstance(node, ast.Lambda):
        result.visit(node.body)
    else:
        for statement in node.body:
            result.visit(statement)
    args = node.args
    argument_names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    argument_names += [a.arg for a in (args.vararg, args.kwarg) if a]
    return result.gettext, '_' in argument_names or '_' in result.bindings


def test_no_gettext_scope_shadows_underscore_across_python_modules():
    for file in SOURCE.rglob('*.py'):
        tree = ast.parse(file.read_text(encoding='utf-8'), filename=str(file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                gettext_used, underscore_bound = _gettext_and_local_binding(node)
                assert not (gettext_used and underscore_bound), (str(file), node.lineno)


def test_locate_again_with_cached_ip_fix_runs_callback_with_gtk_arguments():
    """Execute the actual locate() body through the formerly crashing IP path."""
    method = _class_method(SOURCE / 'ui.py', 'RadarWindow', 'locate')
    namespace = {
        '_': lambda message: 'Tradução: ' + message,
        'GLib': SimpleNamespace(SOURCE_REMOVE=False),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<locate>', 'exec'), namespace)
    calls = []
    mock = SimpleNamespace(
        _last_system_fix=None,
        _last_location_fix=(-20.14, -44.88),
        move_to=lambda *args, **kwargs: calls.append(('move', args, kwargs)),
        _set_my_position=lambda *args: calls.append(('position', args)),
        notify=lambda message: calls.append(('notify', message)),
    )
    namespace['locate'](mock, object())  # GTK Button.clicked passes a widget
    assert calls[0] == ('move', (-20.14, -44.88, 'Tradução: Last approximate IP location', 9),
                        {'animated': True})
    assert calls[1] == ('position', (-20.14, -44.88))
    assert calls[2] == ('notify', 'Tradução: Centering on last approximate IP location.')


def test_favorite_aircraft_in_radar_uses_existing_animated_selection():
    method = _class_method(SOURCE / 'monitor_ui.py', 'SidebarMonitor', '_show_aircraft')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<favorite>', 'exec'), namespace)
    calls = []
    radar = SimpleNamespace(
        records={'a1b2c3': object()},
        select_plane=lambda hexid: calls.append(('select', hexid)),
        focus_global_aircraft=lambda plane: calls.append(('global', plane)),
    )
    namespace['_show_aircraft'](SimpleNamespace(radar=radar), SimpleNamespace(hex='a1b2c3'))
    assert calls == [('select', 'a1b2c3')]
    namespace['_show_aircraft'](SimpleNamespace(radar=radar), SimpleNamespace(hex='deaf00'))
    assert calls[1][0] == 'global'


def test_distant_favorite_uses_animated_map_movement():
    method = _class_method(SOURCE / 'ui.py', 'RadarWindow', 'focus_global_aircraft')
    call = next(n for n in ast.walk(method)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'move_to')
    assert any(key.arg == 'animated' and isinstance(key.value, ast.Constant)
               and key.value.value is True for key in call.keywords)
