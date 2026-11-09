import unittest
from aeroscope.geoview import coverage_for_view, fit_trajectory, initial_bearing

class GeoViewTests(unittest.TestCase):
    def test_bearing(self):
        self.assertAlmostEqual(initial_bearing(0, 0, 0, 1), 90)
        self.assertAlmostEqual(initial_bearing(0, 0, 1, 0), 0)
        self.assertAlmostEqual(initial_bearing(0, 0, 0, -1), 270)
    def test_one_circle(self):
        coverage = coverage_for_view(-20, -44, 10, 700, 600)
        self.assertTrue(coverage.complete)
        self.assertEqual(len(coverage.queries), 1)
        self.assertLessEqual(coverage.queries[0][2], 250)
    def test_wide_view_cap(self):
        coverage = coverage_for_view(-20, -44, 2, 900, 720)
        self.assertLessEqual(len(coverage.queries), 6)
        self.assertFalse(coverage.complete)
    def test_history_fits(self):
        view = fit_trajectory([[(-23.4, -46.4), (-19.6, -43.9)]], 1000, 750)
        self.assertIsNotNone(view)
        self.assertTrue(-24 < view[0] < -19)
        self.assertTrue(2 <= view[2] <= 15)
    def test_dateline(self):
        view = fit_trajectory([[(0, 179.7), (0, -179.6)]], 800, 600)
        self.assertTrue(abs(view[1]) > 170)
