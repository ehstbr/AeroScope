"""Regressions for the tower rings and the main header in 0.3.30."""
from pathlib import Path
import ast

UI = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text()


def _function(name):
    tree = ast.parse(UI)
    for cls in (x for x in tree.body if isinstance(x, ast.ClassDef)):
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.get_source_segment(UI, node)
    raise AssertionError(name)


def test_cairo_does_not_join_label_to_next_circle():
    draw = _function('_draw_radar')
    assert 'cr.new_path()' in draw
    assert draw.index('cr.new_path()') < draw.index('cr.arc(cx, cy, r, 0, math.tau)')
    assert 'cr.show_text(label)\n            cr.new_path()' in draw


def test_header_shortcuts_corrected_in_031():
    build = _function('_build_ui')
    assert "icon_name='view-refresh-symbolic'" in build
    assert 'refresh_button.set_menu_model(refresh_menu)' in build
    assert "header.pack_end(appmenu)" in build
    assert 'header.pack_start(location_menu)' not in build
    # Refresh remains accessible in the sidebar monitoring actions.
    monitor = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'monitor_ui.py').read_text()
    assert 'view-refresh-symbolic' in monitor
