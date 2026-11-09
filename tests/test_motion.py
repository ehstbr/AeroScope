import math
import unittest
from aeroscope.motion import (interpolate_position, PositionTransition, transition_allowed,
                              startup_poll_interval, flight_animation_duration, RequestLatencyTracker)


class MotionTests(unittest.TestCase):
    def test_interpolated_position_and_completion(self):
        segment = PositionTransition((-20.0, -44.0), (-19.9, -43.8), 100.0, 2.0)
        self.assertEqual(segment.sample(99.0), ((-20.0, -44.0), False))
        mid, done = segment.sample(101.0)
        self.assertFalse(done)
        self.assertAlmostEqual(mid[0], -19.95)
        self.assertAlmostEqual(mid[1], -43.9)
        self.assertEqual(segment.sample(102.5), ((-19.9, -43.8), True))

    def test_crossing_dateline_uses_short_arc(self):
        lat, lon = interpolate_position((0, 179.7), (0, -179.7), .5)
        self.assertAlmostEqual(lat, 0)
        self.assertAlmostEqual(abs(lon), 180.0)

    def test_position_rejects_jumps_stale_or_identical(self):
        a = (-20.0, -44.0)
        self.assertTrue(transition_allowed(a, (-19.95, -44), 30))
        self.assertFalse(transition_allowed(a, (-18, -44), 30))
        self.assertTrue(transition_allowed(a, (-19.95, -44), 120))
        self.assertFalse(transition_allowed(a, (-19.95, -44), 181))
        self.assertFalse(transition_allowed(a, (-19.7, -44), 15))
        self.assertFalse(transition_allowed(a, a, 30))
        self.assertFalse(transition_allowed(a, (math.nan, 10), 30))

    def test_no_extrapolation(self):
        segment = PositionTransition((10, 20), (11, 21), 0.0, 2.5)
        self.assertEqual(segment.sample(200)[0], (11.0, 21.0))

    def test_live_update_uses_shared_animation_timer(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text()
        prefs = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'preferences.py').read_text()
        self.assertIn("if changed else 'keep'", src)
        self.assertIn('duration=self._animation_window', src)
        self.assertIn('GLib.timeout_add(40, self._animation_tick)', src)
        self.assertIn('self._next_poll_due', src)
        self.assertIn('if not value:', src)
        self.assertIn("on_change('animate_aircraft', value)", prefs)

    def test_constant_speed_animation(self):
        segment = PositionTransition((0, 0), (0, 10), 10, 40)
        self.assertAlmostEqual(segment.sample(20)[0][1], 2.5)
        self.assertAlmostEqual(segment.sample(30)[0][1], 5.0)
        self.assertAlmostEqual(segment.sample(40)[0][1], 7.5)

    def test_progressive_poll_and_margin(self):
        self.assertEqual([startup_poll_interval(30, n) for n in range(1, 5)],
                         [2.5, 5.0, 30.0, 30.0])
        self.assertEqual([startup_poll_interval(60, n) for n in range(1, 5)],
                         [2.5, 5.0, 60.0, 60.0])
        self.assertAlmostEqual(flight_animation_duration(30), 29.4)
        self.assertAlmostEqual(flight_animation_duration(15), 14.625)
        self.assertAlmostEqual(flight_animation_duration(30, 1.1), 30.5)
        self.assertAlmostEqual(flight_animation_duration(10, 0.9), 10.65)
        self.assertEqual(startup_poll_interval(10, 1), 2.5)
        self.assertEqual(startup_poll_interval(10, 2), 5.0)
        self.assertEqual(startup_poll_interval(10, 3), 10.0)
        self.assertEqual(startup_poll_interval(10, 1, failed=True), 10.0)


    def test_adaptive_latency_uses_five_recent_successes(self):
        tracker = RequestLatencyTracker()
        self.assertEqual(tracker.estimate, 0.0)
        for t in (0.8, 1.0, 1.2, 0.9, 1.1, 0.7):
            tracker.observe(t)
        self.assertEqual(len(tracker.samples), 5)
        self.assertAlmostEqual(tracker.estimate, (1.0+1.2+0.9+1.1+0.7) / 5)

    def test_rejects_bad_latency_and_soft_caps_single_spike(self):
        tracker = RequestLatencyTracker()
        for t in (0.8, 1.0):
            tracker.observe(t)
        tracker.observe(38.0)
        self.assertLess(tracker.estimate, 2.0)
        previous = tracker.estimate
        for t in (float('nan'), float('inf'), -1, 0):
            tracker.observe(t)
        self.assertEqual(previous, tracker.estimate)

    def test_duration_never_extrapolates_position(self):
        duration = flight_animation_duration(10, 1.4)
        self.assertGreater(duration, 10)
        segment = PositionTransition((1, 2), (1.5, 2.5), 0, duration)
        self.assertEqual(segment.sample(duration + 60)[0], (1.5, 2.5))

    def test_elapsed_time_is_measured_at_request_boundaries(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text()
        self.assertIn('self._active_request_started = time.monotonic()', source)
        self.assertIn('self._request_latency.observe(elapsed)', source)
        self.assertIn('next_seconds, self._request_latency.estimate', source)
        self.assertIn("'aeroscope.motion'", source)

    def test_settings_persist_animation_choice(self):
        from aeroscope import settings
        self.assertIn('animate_aircraft', settings.DEFAULT)
        self.assertTrue(settings.DEFAULT['animate_aircraft'])


if __name__ == '__main__':
    unittest.main()
