import unittest
from unittest.mock import patch
from aeroscope import data

class IPLocationTests(unittest.TestCase):
    @patch.object(data, 'read_json')
    def test_success(self, mock):
        mock.return_value = {'success': True, 'latitude': -20.14, 'longitude': -44.89,
                             'city': 'Divinópolis', 'region': 'Minas Gerais', 'country': 'Brazil', 'ip': 'X.X.X.X'}
        lat, lon, place = data.geolocate_by_public_ip()
        self.assertEqual((lat, lon), (-20.14, -44.89))
        self.assertIn('Divinópolis', place)
        mock.assert_called_once_with('https://ipwho.is/', timeout=10)
        self.assertNotIn('X.X.X.X', str((lat, lon, place)))

    @patch.object(data, 'read_json', return_value={'success': False, 'message': 'Rate limit'})
    def test_error(self, mock):
        with self.assertRaisesRegex(RuntimeError, 'Rate limit'):
            data.geolocate_by_public_ip()

    @patch.object(data, 'read_json', return_value={'success': True, 'latitude': 91, 'longitude': 0})
    def test_invalid_coordinates(self, mock):
        with self.assertRaisesRegex(RuntimeError, 'coordenadas inválidas'):
            data.geolocate_by_public_ip()

    def test_ui_requires_consent(self):
        from pathlib import Path
        ui = (Path(__file__).resolve().parents[1] / 'aeroscope/ui.py').read_text()
        self.assertIn("_('Approximate IP location')", ui)
        self.assertIn("if response == 'proceed'", ui)
        self.assertIn('self._async(geolocate_by_public_ip', ui)
        self.assertNotIn('GLib.timeout_add_seconds(2, self.confirm_ip_location)', ui)

if __name__ == '__main__': unittest.main()
