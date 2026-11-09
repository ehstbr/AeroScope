"""Tests for ADSB.lol routeset metadata + geographic (not flown) route."""
import io
import unittest
from unittest.mock import patch
import urllib.error

from aeroscope.routes import (parse_routeset, great_circle_points, map_segments,
                              RouteCache, ProbableRoute)
from aeroscope.data import fetch_live_route, RateLimitError
from aeroscope.geoview import distance_nm, fit_trajectory


EXAMPLE = [{
    'callsign': 'GLO1234', '_airport_codes_iata': 'CNF-GRU',
    '_airports': [
        {'name': 'Confins', 'iata': 'CNF', 'icao': 'SBCF', 'lat': -19.6244, 'lon': -43.9719},
        {'name': 'Guarulhos', 'iata': 'GRU', 'icao': 'SBGR', 'lat': -23.4356, 'lon': -46.4731},
    ], 'plausible': True,
}]

class FakeResponse:
    def __init__(self, content): self.content = content
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, limit=None): return self.content

class RouteTests(unittest.TestCase):
    def test_parse_real_shape(self):
        route = parse_routeset(EXAMPLE, 'glo1234')
        self.assertIsInstance(route, ProbableRoute)
        self.assertEqual(route.origin.code, 'CNF')
        self.assertEqual(route.destination.icao, 'SBGR')
        self.assertTrue(route.plausible)

    def test_route_mismatch_and_missing_coords_rejected(self):
        self.assertIsNone(parse_routeset(EXAMPLE, 'TAM5678'))
        bad = [{**EXAMPLE[0], '_airports': [
            {'iata': 'CNF', 'lat': '-999', 'lon': 2}, EXAMPLE[0]['_airports'][1]]}]
        self.assertIsNone(parse_routeset(bad, 'GLO1234'))
        self.assertIsNone(parse_routeset({}, 'GLO1234'))

    def test_incertain_status_is_preserved_not_claimed_confirmed(self):
        candidate = [{**EXAMPLE[0], 'plausible': False}]
        self.assertFalse(parse_routeset(candidate, 'GLO1234').plausible)

    def test_great_circle_ends_at_airports_and_fits(self):
        a, b = EXAMPLE[0]['_airports']
        points = great_circle_points(a['lat'], a['lon'], b['lat'], b['lon'])
        self.assertEqual(points[0], (a['lat'], a['lon']))
        self.assertEqual(points[-1], (b['lat'], b['lon']))
        self.assertIsNotNone(fit_trajectory([points, [(-21.0, -44.0)]], 900, 640))
        self.assertEqual(len(map_segments(points)), 1)
        self.assertTrue(all(-85 <= lat <= 85 and -180 <= lon <= 180 for lat, lon in points))

    def test_antimeridian_segments_do_not_draw_wrong_side_of_world(self):
        pts = great_circle_points(30, 175, 35, -175)
        segs = map_segments(pts)
        self.assertEqual(len(segs), 2)
        self.assertTrue(all(abs(b[1]-a[1]) < 180 for seg in segs for a,b in zip(seg, seg[1:])))

    def test_cache_success_and_negative_cache(self):
        cache = RouteCache(success_ttl=300, miss_ttl=15)
        key = ('abc123', 'GLO1234')
        self.assertFalse(cache.get(key)[0])
        cache.put(key, parse_routeset(EXAMPLE, 'GLO1234'))
        self.assertTrue(cache.get(key)[0])
        cache.put(('abc123','TAM5678'), None, 'Indisponível')
        self.assertEqual(cache.get(('abc123','TAM5678')), (True, None, 'Indisponível'))
        cache.clear()
        self.assertFalse(cache.get(key)[0])

    @patch('aeroscope.data.urllib.request.urlopen')
    def test_post_uses_current_aircraft_position(self, openurl):
        import json
        openurl.return_value = FakeResponse(json.dumps(EXAMPLE).encode('utf8'))
        route = fetch_live_route('GLO1234', -20.14, -44.89)
        self.assertEqual(route.destination.code, 'GRU')
        request = openurl.call_args.args[0]
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.full_url, 'https://api.adsb.lol/api/0/routeset')
        body = json.loads(request.data)
        self.assertEqual(body['planes'], [{'callsign':'GLO1234','lat':-20.14,'lng':-44.89}])

    def test_invalid_callsign_does_not_make_request(self):
        self.assertIsNone(fetch_live_route('', -20, -45))
        self.assertIsNone(fetch_live_route('$$bad$', -20, -45))

    @patch('aeroscope.data.urllib.request.urlopen')
    def test_429_backoff(self, openurl):
        import email.message
        hdr = email.message.Message()
        hdr['Retry-After'] = '180'
        openurl.side_effect = urllib.error.HTTPError('https://api.adsb.lol/api/0/routeset', 429, 'Limit', hdr, None)
        with self.assertRaises(RateLimitError) as catcher:
            fetch_live_route('GLO1234', -20, -45)
        self.assertEqual(catcher.exception.retry_after, 180)

    def test_ui_is_labeled_probable_and_cleanly_separated(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1]/'aeroscope/ui.py').read_text()
        self.assertIn('Probable route by callsign', source)
        self.assertIn('estimated route', source.lower())
        self.assertIn('self.route_cache', source)
        self.assertIn('self.route_airport_layer', source)
        self.assertIn('self._clear_route_visual()', source)
        self.assertIn('not self._route_camera', source)

if __name__ == '__main__':
    unittest.main()
