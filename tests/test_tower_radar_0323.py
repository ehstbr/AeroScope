"""Regression checks for full-viewport sweep and aircraft-relative clock."""
import math
from pathlib import Path
import unittest
from aeroscope.tower_radar import (
    full_map_radius, clock_hour_bearings, clock_ring_radius,
    ring_label_anchor, meters_per_pixel,
)


class TowerOverlayGeometryTests(unittest.TestCase):
    def test_full_radius_reaches_all_four_corners_on_wide_map(self):
        for width, height in ((1600, 900), (420, 900), (1920, 1080)):
            r = full_map_radius(width, height)
            for x, y in ((0, 0), (width, 0), (0, height), (width, height)):
                self.assertGreaterEqual(r + 1e-8, math.hypot(x-width/2, y-height/2))
        self.assertAlmostEqual(full_map_radius(1600, 900), math.hypot(800, 450))

    def test_clock_12_and_2_oclock_rotate_with_aircraft_nose(self):
        self.assertEqual(clock_hour_bearings(0)[0], 0)
        self.assertEqual(clock_hour_bearings(0)[2], 60)
        self.assertEqual(clock_hour_bearings(90)[0], 90)
        self.assertEqual(clock_hour_bearings(90)[2], 150)
        self.assertEqual(clock_hour_bearings(315)[2], 15)
        self.assertEqual(clock_hour_bearings(270)[6], 90)
        self.assertEqual(len(set(clock_hour_bearings(90))), 12)

    def test_clock_maintains_fixed_size_as_aircraft_nears_edge(self):
        self.assertAlmostEqual(clock_ring_radius(1600, 900, 800, 450), 168)
        self.assertAlmostEqual(clock_ring_radius(1600, 900, 100, 100), 168)
        self.assertAlmostEqual(clock_ring_radius(1600, 900, 5, 300), 168)
        self.assertAlmostEqual(clock_ring_radius(1600, 900, 1500, 5), 168)
        self.assertEqual(clock_ring_radius(240, 300, 0, 0), 96)

    def test_ring_labels_are_visible_at_initial_draw(self):
        # No location conversion/GTK initial allocation is required.
        self.assertGreater(meters_per_pixel(-20.14, 9), 0)
        width, height = 1600, 900
        for part in (.25, .50, .75, 1):
            x, y = ring_label_anchor(width/2, height/2,
                                     full_map_radius(width, height)*.88*part,
                                     width, height, 68)
            self.assertTrue(0 <= x <= width - 68)
            self.assertTrue(0 <= y <= height - 22)

    def test_ui_reveals_only_on_sweep_and_centers_clock_on_visible_aircraft(self):
        src = (Path(__file__).resolve().parents[1]/'aeroscope'/'ui.py').read_text()
        self.assertIn('def _draw_relative_clock', src)
        self.assertIn('def _selected_tower_reference', src)
        self.assertIn('clock_hour_bearings(heading)', src)
        self.assertIn('full_map_radius(width, height, cx, cy)', src)
        self.assertIn('self._tower_ring_distance_nm(cx, cy, r)', src)
        self.assertIn('self._sweep_pending[plane.hex] = (', src)
        self.assertIn("bearing=marker.bearing, position_mode='keep'", src)
        self.assertIn('marker.transition = PositionTransition(start, target, now, glide)', src)
        self.assertIn('virtual.sample(now)', src)
        self.assertIn('self._sweep_virtual[plane.hex] = PositionTransition(', src)
        self.assertNotIn('changed and self._tower_sweep_enabled() and self._sweep_marker_bearing(marker) is not None', src)
        self.assertIn("locate.set_margin_end(13)",
                      (Path(__file__).resolve().parents[1]/'aeroscope'/'monitor_ui.py').read_text())


if __name__ == '__main__':
    unittest.main()
