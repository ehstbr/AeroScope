"""Regression checks for GTK map hit testing and Planespotters reuse.

The test runner may not have GI/GTK, so isolate the decision methods and
exercise them against small fake GTK objects.
"""
import ast
import math
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text('utf-8')
ROOT = ast.parse(SOURCE)
WINDOW = next(n for n in ROOT.body if isinstance(n, ast.ClassDef) and n.name == 'RadarWindow')


def extract(name, namespace):
    method = next(n for n in WINDOW.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    method.decorator_list = []
    isolated = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(isolated, '<isolated UI method>', 'exec'), namespace)
    return namespace[name]


class FakeButton:
    def __init__(self, parent=None):
        self.parent = parent
    def get_parent(self):
        return self.parent

class FakeWidget:
    def __init__(self, parent=None):
        self.parent = parent
    def get_parent(self):
        return self.parent

class FakeOverlay(FakeWidget):
    def __init__(self, hit):
        super().__init__()
        self.hit = hit
    def pick(self, x, y, flags):
        return self.hit

class FakeViewport:
    def __init__(self):
        self.lat = -20.14
        self.lon = -44.89
    def get_latitude(self): return self.lat
    def get_longitude(self): return self.lon

class BlankMapTests(unittest.TestCase):
    def setUp(self):
        namespace = dict(math=math, Gtk=SimpleNamespace(Button=FakeButton,
                          PickFlags=SimpleNamespace(DEFAULT=0)))
        self.pressed = extract('_map_click_pressed', namespace)
        self.released = extract('_map_click_released', namespace)
        self.win = SimpleNamespace(selected_hex='e48df5', selected_airport=None,
                                   viewport=FakeViewport(), _map_press_position=None)
        self.cleared = []
        self.win._clear_selected = lambda: self.cleared.append(True)
        self.win.map_overlay = FakeOverlay(None)

    def press(self): self.pressed(self.win, None, 1, 30, 60)
    def release(self, x=30, y=60): self.released(self.win, None, 1, x, y)

    def test_blank_map_click_clears_selection(self):
        self.press()
        self.win.map_overlay.hit = FakeWidget(self.win.map_overlay)
        self.release()
        self.assertEqual(self.cleared, [True])

    def test_aircraft_or_airport_button_does_not_deselect(self):
        self.press()
        button = FakeButton(self.win.map_overlay)
        self.win.map_overlay.hit = FakeWidget(button)
        self.release()
        self.assertFalse(self.cleared)

    def test_drag_does_not_deselect(self):
        self.press()
        self.win.map_overlay.hit = FakeWidget(self.win.map_overlay)
        self.release(90, 60)
        self.assertFalse(self.cleared)

    def test_camera_movement_does_not_deselect(self):
        self.press()
        self.win.viewport.lon += 0.001
        self.release()
        self.assertFalse(self.cleared)

    def test_double_click_does_not_deselect(self):
        self.pressed(self.win, None, 2, 30, 60)
        self.release()
        self.assertFalse(self.cleared)


class PhotoWidgetReuseTests(unittest.TestCase):
    def test_one_cached_decoding_per_selected_aircraft(self):
        self.assertIn('self.photo_widgets[hexid] = self._make_photo_widget', SOURCE)
        self.assertIn('self.detail_box.append(self.photo_widgets[hexid])', SOURCE)
        self.assertIn('self.photo_widgets.pop(hexid, None)', SOURCE)
        self.assertIn('self._show_photo_preview(hexid, photo, texture, registration)', SOURCE)

    def test_gallery_paths_normalized_and_safe(self):
        fn = extract('_photo_gallery_url', dict(re=re))
        self.assertEqual(fn('pt-muj'), 'https://www.planespotters.net/photos/reg/PT-MUJ')
        self.assertIsNone(fn('../example'))
        self.assertIsNone(fn('PT-MUJ/abc'))

    def test_original_link_opens_internal_viewer(self):
        self.assertIn("self._view_website(url, _('Original photo'))", SOURCE)
        self.assertIn("self._view_website(gallery_url, 'Galeria", SOURCE)


if __name__ == '__main__':
    unittest.main()
