import unittest
from unittest.mock import patch
from aeroscope.data import fetch_history_index, fetch_history_path, fetch_photo_details

class EnrichmentTest(unittest.TestCase):
    @patch('aeroscope.data._post_json')
    def test_history_request(self, post):
        post.return_value = {'flights': [{'flight_id': 'a1b2c3:2026-09-01T12:00:00Z'}]}
        res = fetch_history_index('A1B2C3')
        self.assertEqual(len(res), 1)
        self.assertEqual(post.call_args.args[1]['match'], {'icao24':['a1b2c3']})
        self.assertFalse(post.call_args.args[1]['include_path'])
    @patch('aeroscope.data.read_json')
    def test_gaps_are_preserved(self, read):
        read.return_value = {'path': {'type': 'MultiLineString', 'coordinates': [
            [[-44.0,-20.0,12000], [-43.0,-19.0,14000]],
            [[-42.0,-18.0,16000], [-41.0,-17.0,18000]]
        ]}}
        self.assertEqual(fetch_history_path('a1b2c3:2026-09-01T12:00:00Z'),
                         [[(-20.,-44.), (-19.,-43.)], [(-18.,-42.), (-17.,-41.)]])
    @patch('aeroscope.data._photo_json_get')
    def test_photo_host_validation(self, read):
        read.return_value = {'photos': [{'thumbnail': {'src': 'https://evil.example/image.jpg'}, 'link':'https://www.planespotters.net/abc'}]}
        self.assertIsNone(fetch_photo_details('a1b2c3'))

if __name__ == '__main__':
    unittest.main()
