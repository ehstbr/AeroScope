"""Regression tests for start-up warmup and GNOME preparation window."""
import unittest
from pathlib import Path
from aeroscope.motion import startup_poll_interval, flight_animation_duration
from aeroscope.settings import DEFAULT

ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def test_exact_startup_cadence(self):
        self.assertEqual([startup_poll_interval(10, i) for i in (1, 2, 3, 4)],
                         [2.5, 5.0, 10.0, 10.0])
        self.assertEqual([startup_poll_interval(30, i) for i in (1, 2, 3, 4)],
                         [2.5, 5.0, 30.0, 30.0])

    def test_normal_cadence_has_ten_second_floor(self):
        self.assertEqual(startup_poll_interval(0, 3), 10.0)
        self.assertEqual(startup_poll_interval(5, 4), 10.0)
        self.assertEqual(startup_poll_interval(120, 5), 120.0)

    def test_failures_skip_further_burst(self):
        self.assertEqual(startup_poll_interval(10, 1, failed=True), 10.0)
        self.assertEqual(startup_poll_interval(30, 2, failed=True), 30.0)

    def test_preferences_persist_startup_option(self):
        prefs = (ROOT / 'aeroscope' / 'preferences.py').read_text()
        self.assertTrue(DEFAULT['startup_splash'])
        self.assertEqual(DEFAULT['refresh'], 10)
        self.assertIn("on_change('startup_splash', value)", prefs)
        self.assertIn('delays = list(INTERVALS)', prefs)
        self.assertIn('background_delays = list(BACKGROUND_INTERVALS)', prefs)
        self.assertIn("_('Show startup preparation')", prefs)

    def test_modal_closes_on_three_successes_or_failure(self):
        ui = (ROOT / 'aeroscope' / 'ui.py').read_text()
        self.assertIn('Adw.Dialog()', ui)
        self.assertIn('dialog.present(self)', ui)
        self.assertIn('if count >= 3:', ui)
        self.assertIn('self._finish_startup()  # do not block', ui)
        self.assertIn('GLib.timeout_add_seconds(22, self._startup_watchdog)', ui)
        self.assertIn('GLib.timeout_add(250, self._timer_refresh)', ui)

    def test_motion_duration_matches_warmup(self):
        self.assertAlmostEqual(flight_animation_duration(2.5), 2.35)
        self.assertAlmostEqual(flight_animation_duration(5), 4.85)
        self.assertAlmostEqual(flight_animation_duration(10), 9.75)


if __name__ == '__main__':
    unittest.main()
