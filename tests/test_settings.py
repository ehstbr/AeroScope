import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aeroscope import settings

class SettingsTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(settings, 'CONFIG_DIR', Path(tmp)):
                data = settings.load()
                self.assertEqual(data['theme'], 'system')
                data['theme'] = 'dark'
                settings.save(data)
                self.assertEqual(settings.load()['theme'], 'dark')
                self.assertEqual(json.loads((Path(tmp)/'settings.json').read_text())['theme'], 'dark')
    def test_app_cache_cannot_delete_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(settings, 'CACHE_DIR', Path(tmp)/'cache'), patch.object(settings, 'CONFIG_DIR', Path(tmp)/'config'):
                settings.save(settings.DEFAULT)
                settings.CACHE_DIR.mkdir()
                (settings.CACHE_DIR/'temp.txt').write_text('test')
                settings.clear_cache()
                self.assertFalse((settings.CACHE_DIR/'temp.txt').exists())
                self.assertTrue((settings.CONFIG_DIR/'settings.json').exists())

if __name__ == '__main__':
    unittest.main()
