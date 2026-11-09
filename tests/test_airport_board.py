import unittest
from aeroscope.data import airport_board_url

class AirportBoardTests(unittest.TestCase):
    def test_safe_airport_urls(self):
        self.assertEqual(airport_board_url('GRU'), 'https://www.flightradar24.com/data/airports/gru')
        self.assertEqual(airport_board_url('cnf'), 'https://www.flightradar24.com/data/airports/cnf')
    def test_invalid_airport(self):
        with self.assertRaises(ValueError): airport_board_url('https://example.com')
        with self.assertRaises(ValueError): airport_board_url('ZZZ')
