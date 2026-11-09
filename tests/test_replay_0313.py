"""Time-indexed historical replay, route flexibility and privacy regression."""
import json
import unittest
from unittest.mock import patch

from aeroscope.playback import parse_historical_replay
from aeroscope.routes import parse_routeset, route_has_geometry
from aeroscope.data import fetch_history_replay, AIRPORTS
from aeroscope.settings import DEFAULT

PAYLOAD = {
    'path': {'type': 'MultiLineString', 'coordinates': [
        [[-44.0, -20.0, 10000], [-43.8, -19.9, 12000]],
        [[-43.0, -19.2, 20000], [-42.9, -19.1, 21000]],
    ]},
    'timestamps': [[100.0, 110.0], [190.0, 200.0]],
    'path_gs': [[[100.0, 300]], [[190.0, 400]]],
}


class FakeResponse:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, *_): return self.data


class ReplayTests(unittest.TestCase):
    def test_time_synced_interpolation(self):
        track = parse_historical_replay(PAYLOAD)
        self.assertEqual(track.duration, 100)
        p = track.seek(105)
        self.assertAlmostEqual(p.lat, -19.95)
        self.assertAlmostEqual(p.lon, -43.9)
        self.assertAlmostEqual(p.altitude_ft, 11000)
        self.assertFalse(p.coverage_gap)

    def test_gap_is_not_interpolated(self):
        track = parse_historical_replay(PAYLOAD)
        p = track.seek(150)
        self.assertEqual((p.lat, p.lon), (-19.9, -43.8))
        self.assertTrue(p.coverage_gap)
        self.assertEqual(len(track.visible_segments(150)), 1)
        self.assertEqual(track.visible_segments(150)[0][-1], (-19.9, -43.8))
        self.assertEqual(len(track.visible_segments(195)), 2)

    def test_disallows_synthetic_time_if_timestamps_missing(self):
        self.assertIsNone(parse_historical_replay({'path': PAYLOAD['path']}))
        self.assertIsNone(parse_historical_replay({'path': PAYLOAD['path'], 'timestamps': [[100]]}))

    def test_timestamp_alignment_and_invalid_coordinates(self):
        data = json.loads(json.dumps(PAYLOAD))
        data['timestamps'][0] = [100.0]
        track = parse_historical_replay(data)
        self.assertEqual(len(track.segments), 1)
        self.assertEqual(track.start, 190.0)

    def test_seek_clamped_and_paused_end(self):
        track = parse_historical_replay(PAYLOAD)
        self.assertEqual(track.seek(-50).lat, -20)
        self.assertEqual(track.seek(500).lat, -19.1)

    def test_dateline_uses_shortest_lon(self):
        track = parse_historical_replay({'path': {'type':'MultiLineString',
            'coordinates': [[[179.0, 0.0],[-179.0, 0.0]]]},
            'timestamps': [[100.0, 110.0]]})
        self.assertAlmostEqual(abs(track.seek(105).lon), 180.0)

    @patch('aeroscope.data.urllib.request.urlopen')
    def test_api_full_trajectory_with_time(self, openurl):
        openurl.return_value = FakeResponse(json.dumps(PAYLOAD).encode())
        track = fetch_history_replay('e48df5:2026-11-06T12:30:00Z')
        self.assertEqual(len(track.segments), 2)
        self.assertIn('/flights/e48df5:', openurl.call_args.args[0].full_url)

    def test_origin_dest_uses_all_documented_formats(self):
        airports = [{'iata':'CNF', 'lat':-19.6244,'lon':-43.9719},
                    {'iata':'GRU', 'lat':-23.4356,'lon':-46.4731}]
        candidate = {'callsign':'GLO1234','_airports':airports,'plausible':True}
        for payload in ([candidate], {'routes':[candidate]},
                        json.dumps([candidate]), json.dumps(json.dumps([candidate]))):
            r = parse_routeset(payload, 'GLO1234', AIRPORTS)
            self.assertIsNotNone(r)
            self.assertEqual(r.origin.code, 'CNF')
        code_only = {'planes': [{'callsign':'GLO1234', '_airport_codes_iata':'CNF-GRU'}]}
        r = parse_routeset(code_only, 'GLO1234', AIRPORTS)
        self.assertEqual(r.destination.code, 'GRU')
        self.assertAlmostEqual(r.destination.lat, AIRPORTS['GRU'][2])

    def test_unknown_airport_code_is_shown_without_inventing_coordinates(self):
        route = parse_routeset([{'callsign':'XAB123','airport_codes':'AAAA-BBBB'}],
                               'XAB123', AIRPORTS)
        self.assertEqual(route.origin.code, 'AAAA')
        self.assertEqual(route.destination.code, 'BBBB')
        self.assertIsNone(route.origin.lat)
        self.assertFalse(route_has_geometry(route))

    def test_privacy_opt_in_default(self):
        self.assertFalse(DEFAULT['ip_disclosure_accepted'])
        self.assertTrue(DEFAULT['suggest_ip_fallback'])

    def test_ui_has_replay_controls_and_header_coverage(self):
        from pathlib import Path
        code = (Path(__file__).resolve().parents[1] / 'aeroscope/ui.py').read_text()
        for token in ('self.replay_panel', "['1×', '2×', '4×', '8×']",
                      'Hide live aircraft', 'self.replay_marker_layer',
                      'self.window_title.set_subtitle',
                      "self.settings['ip_disclosure_accepted'] = True"):
            self.assertIn(token, code)


if __name__ == '__main__': unittest.main()
