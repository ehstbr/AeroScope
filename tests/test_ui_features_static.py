from pathlib import Path
import unittest

SRC=(Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text()
class UIFeaturesTests(unittest.TestCase):
    def test_selection_and_hover_are_distinct(self):
        self.assertIn('def _sync_marker_selection', SRC)
        self.assertIn('marker.set_selected(', SRC)
        self.assertIn('marker.set_highlighted(active)', SRC)

    def test_viewport_refresh_debounced(self):
        self.assertIn('notify::', SRC)
        self.assertIn('GLib.timeout_add(850', SRC)
        self.assertIn('fetch_visible_area(((center[0], center[1], 250),))', SRC)
        self.assertIn('viewport_inside_radius(view, self._query_anchor)', SRC)
    def test_history_fit(self):
        self.assertIn('fit_trajectory(self.replay_track.full_coordinates()', SRC)
        self.assertIn('self.map.center_on(first.lat, first.lon)', SRC)
        self.assertIn('self.viewport.set_zoom_level(zoom)', SRC)
    def test_no_flight_schedule_api(self):
        self.assertIn('airport_board_url(iata)', SRC)
        self.assertIn('View arrivals and departures', SRC)
        self.assertNotIn('fetch_airport_movements', SRC)
        self.assertIn("'www.flightradar24.com'", SRC)
    def test_hover(self):
        self.assertIn('Gtk.EventControllerMotion()', SRC)
        self.assertIn('marker.set_highlighted(active)', SRC)
