"""Static GTK4 enum regression checks, no display or GI modules required."""
import ast
import unittest
from pathlib import Path

class UIStaticTest(unittest.TestCase):
    def test_gtk4_align_enum_values(self):
        p = Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py'
        root = ast.parse(p.read_text(encoding='utf-8'))
        allowed = {'START', 'END', 'CENTER', 'FILL', 'BASELINE', 'BASELINE_FILL', 'BASELINE_CENTER'}
        for node in ast.walk(root):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name) and node.value.value.id == 'Gtk'
                and node.value.attr == 'Align'):
                self.assertIn(node.attr, allowed, f'Enum GTK4 inválido na linha {node.lineno}: {node.attr}')

class GnomeLayoutRegressionTests(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text(encoding='utf-8')

    def test_zoom_controls_not_duplicated(self):
        self.assertIn('self.simple_map.set_show_zoom_buttons(False)', self.source)
        self.assertIn('self.map_overlay.add_overlay(map_controls)', self.source)
        self.assertNotIn("icon_button('zoom-in-symbolic'", self.source)
        self.assertNotIn("icon_button('zoom-out-symbolic'", self.source)
        self.assertNotIn('map_overlay.add_overlay(toolbar)', self.source)

    def test_aircraft_cursor_is_distinct_from_drag(self):
        self.assertIn("self.button.set_cursor_from_name('zoom-in')", self.source)
        self.assertIn('Clique para ver os detalhes', self.source)

    def test_native_app_chrome(self):
        self.assertIn('Adw.ToolbarView()', self.source)
        self.assertIn('Adw.HeaderBar()', self.source)
        self.assertIn('Adw.WindowTitle(', self.source)
        self.assertIn('self.window_title.set_subtitle(message)', self.source)
        self.assertNotIn('layout.add_bottom_bar(status)', self.source)

if __name__ == '__main__':
    unittest.main()
