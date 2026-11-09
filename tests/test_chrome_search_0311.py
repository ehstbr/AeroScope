"""GNOME chrome/search regression tests without a graphical display."""
import ast
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text('utf8')


class WindowChromeAndSearchTests(unittest.TestCase):
    def test_status_uses_header_subtitle_and_map_has_no_footer(self):
        self.assertIn("self.window_title = Adw.WindowTitle", SRC)
        self.assertIn("self.window_title.set_subtitle(message)", SRC)
        self.assertNotIn("layout.add_bottom_bar(status)", SRC)
        self.assertNotIn("self.hud_text", SRC)

    def test_support_maps_is_not_on_map(self):
        self.assertIn("menu.append(_('Support map providers'), 'app.support-maps')", SRC)
        self.assertIn("'https://openmaps.fr/donate'", SRC)
        self.assertNotIn("Gtk.LinkButton.new_with_label('https://openmaps.fr/donate'", SRC)

    def test_autocomplete_is_inline_and_not_popup_surface(self):
        self.assertIn('self.suggestions_revealer = Gtk.Revealer()', SRC)
        self.assertIn('top.append(self.suggestions_revealer)', SRC)
        self.assertNotIn('self.suggestions_popover', SRC)
        self.assertIn('self._commit_search()', SRC)
        self.assertIn("self.connect('notify::is-active'", SRC)

    def test_geocoder_does_not_reopen_after_search_committed(self):
        tree = ast.parse(SRC)
        win = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'RadarWindow')
        done = next(x for x in win.body if isinstance(x, ast.FunctionDef) and x.name == '_city_suggestions_done')
        snippet = ast.get_source_segment(SRC, done)
        self.assertIn('not self._search_committed', snippet)
        self.assertIn('self.is_active()', snippet)

    def test_main_map_zoom_and_location_are_compact_without_duplicate_native_controls(self):
        self.assertIn('self.simple_map.set_show_zoom_buttons(False)', SRC)
        self.assertIn("geo.add_css_class('mainmap-zoom-button')", SRC)

if __name__ == '__main__':
    unittest.main()
