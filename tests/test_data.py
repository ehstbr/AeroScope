import unittest
from aeroscope.data import parse_aircraft, demo_aircraft, find_airport, Aircraft


class DataTest(unittest.TestCase):
    def test_parses_normal_aircraft(self):
        src = {'ac': [{'hex': 'e49012', 'flight': 'GLO1732 ', 'r': 'PR-ABC',
                        't': 'B738', 'lat': -20.15, 'lon': -44.9,
                        'alt_baro': 32000, 'gs': 420, 'track': 90,
                        'seen_pos': 1.2}]}
        planes = parse_aircraft(src)
        self.assertEqual(len(planes), 1)
        self.assertEqual(planes[0].flight, 'GLO1732')
        self.assertEqual(planes[0].altitude, '32.000 pés')
        self.assertEqual(planes[0].speed, '778 km/h')

    def test_filters_stale_invalid(self):
        rows = [
            {'hex': 'a1', 'lat': -20, 'lon': -44, 'seen_pos': 91},
            {'hex': 'a2', 'lat': None, 'lon': -44},
            {'hex': 'a3', 'lat': -20, 'lon': -44, 'seen_pos': 3, 'alt_baro': 'ground'},
        ]
        planes = parse_aircraft({'ac': rows})
        self.assertEqual([p.hex for p in planes], ['a3'])
        self.assertIsNone(planes[0].altitude_ft)

    def test_airport(self):
        self.assertEqual(find_airport('CNF')[0], 'CNF')
        self.assertEqual(find_airport('SBCF')[0], 'CNF')
        self.assertIsNone(find_airport('ZZZZZZ'))

    def test_demo_changes_position(self):
        first = demo_aircraft(-20.13, -44.88)
        later = demo_aircraft(-20.13, -44.88, 1)
        self.assertEqual(len(first), 8)
        self.assertNotEqual(first[0].lat, later[0].lat)


if __name__ == '__main__':
    unittest.main()
