"""v0.3.14: archival marker, telemetry graph, time and distance controls."""
from pathlib import Path
import math
import unittest

from aeroscope.playback import parse_historical_replay
from aeroscope.replay_chart import (fraction_for_time, time_for_fraction,
                                    metric_bounds, chart_hit_fraction, x_label,
                                    plot_chart)
from aeroscope.aircraft_art import paint_replay_aircraft


PAYLOAD = {
    'path': {'type': 'MultiLineString', 'coordinates': [
        [[-44., -20., 10000], [-43.9, -20., 12000], [-43.8, -20., 14000]],
        [[-43.6, -20., 18000], [-43.5, -20., 20000]],
    ]},
    'timestamps': [[100., 110., 120.], [200., 210.]],
    'path_gs': [[[100., 250], [115., 300]], [[200., 400]]],
}


class Replay0314Tests(unittest.TestCase):
    def setUp(self):
        self.track = parse_historical_replay(PAYLOAD)

    def test_telemetry_uses_independent_sparse_speed_timestamps(self):
        self.assertEqual(self.track.seek(105).speed_kt, 250)
        self.assertEqual(self.track.seek(118).speed_kt, 300)
        self.assertEqual(self.track.seek(205).speed_kt, 400)
        speeds = self.track.series('speed')
        self.assertEqual(speeds[0], [(100,250), (115,250), (115,300), (120,300)])
        self.assertEqual(speeds[1], [(200,400), (210,400)])

    def test_preserve_gaps_without_line_connections(self):
        self.assertEqual(len(self.track.series('altitude')), 2)
        self.assertEqual(len(self.track.series('speed')), 2)
        self.assertTrue(self.track.seek(150).coverage_gap)
        self.assertAlmostEqual(self.track.distance_at(150), self.track.distance_at(120))
        self.assertAlmostEqual(self.track.total_distance_km, self.track.distance_at(210))

    def test_altitude_not_inferred_where_missing(self):
        data = dict(PAYLOAD)
        data['path'] = {'type':'MultiLineString', 'coordinates': [[[-44,-20],[-43.8,-20]]]}
        data['timestamps'] = [[100,120]]
        data['path_gs'] = None
        replay = parse_historical_replay(data)
        self.assertEqual(replay.series('altitude'), [[]])
        self.assertEqual(replay.series('speed'), [[]])
        self.assertIsNone(replay.seek(110).speed_kt)

    def test_aircraft_orientation_uses_neighbouring_points(self):
        bearing = self.track.bearing_at(105)
        self.assertTrue(85 < bearing < 95)
        self.assertTrue(85 < self.track.bearing_at(205) < 95)
        # Frozen position inside gap inherits previous heading, never links
        # a first point of the next segment to the previous segment.
        self.assertAlmostEqual(self.track.bearing_at(150), self.track.bearing_at(120))

    def test_three_axis_modes_and_seek(self):
        track = self.track
        self.assertAlmostEqual(fraction_for_time(track, 100, 'elapsed'), 0)
        self.assertAlmostEqual(fraction_for_time(track, 210, 'clock'), 1)
        self.assertAlmostEqual(time_for_fraction(track, .5, 'elapsed'), 155)
        self.assertAlmostEqual(time_for_fraction(track, .5, 'distance'),
                               track.time_at_distance(track.total_distance_km/2))
        self.assertGreater(track.total_distance_km, 25)
        self.assertTrue(x_label(track, 0, 'distance').endswith('km'))
        self.assertEqual(chart_hit_fraction(-5,800),0)
        self.assertEqual(chart_hit_fraction(900,800),1)

    def test_metric_bounds_and_both_enabled(self):
        self.assertEqual(metric_bounds(self.track,'altitude'), (0,20000))
        self.assertEqual(metric_bounds(self.track,'speed'), (0,400))
        try:
            import cairo
        except ImportError:
            self.skipTest('Cairo not installed in test environment')
        for axis in ('clock','elapsed','distance'):
            surface=cairo.ImageSurface(cairo.FORMAT_ARGB32, 820,250)
            ctx=cairo.Context(surface)
            plot_chart(self.track,ctx,820,250,118,axis=axis,altitude=True,speed=True,dark=True)
            surface.flush()
            self.assertGreater(sum(surface.get_data()),0)
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,56,56)
        ctx=cairo.Context(surface)
        paint_replay_aircraft(ctx,'B738',90)
        surface.flush()
        self.assertGreater(sum(surface.get_data()),0)

    def test_ui_wiring(self):
        ui=(Path(__file__).resolve().parents[1]/'aeroscope/ui.py').read_text()
        for name in ('self.replay_title.set_text', 'self.replay_subtitle.set_text',
                     'paint_replay_aircraft', 'self._replay_fit_full_track',
                     'self.map.center_on(first.lat, first.lon)',
                     "[_('UTC time'), _('Elapsed time'), _('Distance')]",
                     'self.replay_chart_revealer', 'self.replay_chart.queue_draw()',
                     'self._replay_chart_pressed', 'Hide live aircraft'):
            self.assertIn(name,ui)
        self.assertNotIn("Gtk.Label(label='✈')",ui)


if __name__ == '__main__':
    unittest.main()
