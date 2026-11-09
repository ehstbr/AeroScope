import unittest
from aeroscope.aircraft_art import (aircraft_kind, aircraft_name, aircraft_category,
                                   altitude_visual_scale, paint_aircraft)


class AircraftArtTests(unittest.TestCase):
    def test_subtle_altitude_scaling(self):
        self.assertAlmostEqual(altitude_visual_scale(None), 0.9)
        self.assertAlmostEqual(altitude_visual_scale(0), 0.9)
        self.assertGreater(altitude_visual_scale(10000), altitude_visual_scale(0))
        self.assertGreater(altitude_visual_scale(35000), altitude_visual_scale(10000))
        self.assertAlmostEqual(altitude_visual_scale(90000), 1.08)
        self.assertEqual(altitude_visual_scale(float('nan')), 1.0)

    def test_altitude_setting_is_available(self):
        from aeroscope.settings import DEFAULT
        self.assertTrue(DEFAULT['altitude_perspective'])
        from pathlib import Path
        prefs = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'preferences.py').read_text()
        self.assertIn("on_change('altitude_perspective', value)", prefs)

    def test_hover_does_not_use_selection_ring(self):
        import inspect
        source = inspect.getsource(paint_aircraft)
        self.assertIn('elif highlighted:', source)
        self.assertIn('factor * 1.12', source)
        self.assertIn('if selected:', source)

    def test_major_types(self):
        expectations = {
            'B77W': 'widebody', 'A359': 'widebody', 'B738': 'jet',
            'E195': 'regional', 'E295': 'regional', 'AT76': 'turboprop',
            'C172': 'light', 'R44': 'helicopter',
        }
        for model, kind in expectations.items():
            with self.subTest(model=model):
                self.assertEqual(aircraft_kind(model), kind)

    def test_model_descriptions(self):
        self.assertEqual(aircraft_name('b77w'), 'Boeing 777-300ER')
        self.assertEqual(aircraft_name('E295'), 'Embraer E195-E2')
        self.assertEqual(aircraft_category('R44'), 'Helicóptero')
        self.assertEqual(aircraft_name('XXXX'), 'Tipo ICAO XXXX')
        self.assertEqual(aircraft_name(''), 'Modelo não informado')


if __name__ == '__main__':
    unittest.main()
