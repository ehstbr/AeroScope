"""Math + integration checks for the GNOME optional radar beam presentation."""
import unittest
from pathlib import Path
from aeroscope.tower_radar import bearing_on_screen, crossed_clockwise, ring_label, meters_per_pixel
from aeroscope.settings import DEFAULT

class TowerPresentationTests(unittest.TestCase):
    def test_screen_compass(self):
        self.assertAlmostEqual(bearing_on_screen(0, -50), 0)
        self.assertAlmostEqual(bearing_on_screen(10, 0), 90)
        self.assertAlmostEqual(bearing_on_screen(0, 50), 180)
        self.assertAlmostEqual(bearing_on_screen(-10, 0), 270)

    def test_sweep_crossing_and_wrap(self):
        self.assertTrue(crossed_clockwise(356, 4, 359))
        self.assertTrue(crossed_clockwise(356, 4, 1))
        self.assertFalse(crossed_clockwise(356, 4, 190))
        self.assertFalse(crossed_clockwise(30, 60, 15))
        self.assertTrue(crossed_clockwise(30, 60, 15, full_turn=True))

    def test_ring_unit_reuses_speed_preference(self):
        self.assertEqual(ring_label(10, 'kmh'), '19 km')
        self.assertEqual(ring_label(10, 'kt'), '10 NM')
        self.assertEqual(ring_label(10, 'mph'), '12 mi')
        self.assertGreater(meters_per_pixel(0, 8), meters_per_pixel(0, 9))

    def test_defaults_and_ui_wiring(self):
        self.assertTrue(DEFAULT['monitor_emergencies'])
        self.assertTrue(DEFAULT['notify_emergencies'])
        self.assertFalse(DEFAULT['sound_emergencies'])
        self.assertFalse(DEFAULT['tower_sweep'])
        src = (Path(__file__).resolve().parents[1]/'aeroscope'/'ui.py').read_text()
        self.assertIn('self._release_sweep_position(hexid)', src)
        self.assertIn('self.radar_decoration.queue_draw()', src)
        self.assertIn("center = icon_button('find-location-symbolic'", src)

if __name__ == '__main__':
    unittest.main()
