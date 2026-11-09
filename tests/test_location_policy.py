import unittest
from unittest.mock import Mock
from aeroscope.location_policy import is_gnome_desktop, system_location_status, should_suggest_ip

class LocationPolicyTests(unittest.TestCase):
    def test_gnome_desktop(self):
        self.assertTrue(is_gnome_desktop({'XDG_CURRENT_DESKTOP':'ubuntu:GNOME'}))
        self.assertFalse(is_gnome_desktop({'XDG_CURRENT_DESKTOP':'KDE'}))
        self.assertFalse(is_gnome_desktop({'XDG_CURRENT_DESKTOP':'XFCE'}))
        self.assertFalse(is_gnome_desktop({'XDG_CURRENT_DESKTOP':'LXQt'}))

    def test_gnome_disabled_skips_geoclue_even_if_present(self):
        gio = Mock()
        schema = Mock()
        schema.has_key.return_value = True
        gio.SettingsSchemaSource.get_default.return_value.lookup.return_value = schema
        gio.Settings.new.return_value.get_boolean.return_value = False
        status, message = system_location_status(gio, True, {'XDG_CURRENT_DESKTOP':'GNOME'})
        self.assertEqual(status, 'disabled')
        self.assertIn('desativada', message)

    def test_gnome_enabled_uses_geoclue(self):
        gio = Mock()
        gio.SettingsSchemaSource.get_default.return_value.lookup.return_value.has_key.return_value = True
        gio.Settings.new.return_value.get_boolean.return_value = True
        self.assertEqual(system_location_status(gio, True, {'XDG_CURRENT_DESKTOP':'GNOME'})[0], 'try')

    def test_kde_does_not_read_gnome_preferences(self):
        gio = Mock()
        self.assertEqual(system_location_status(gio, True, {'XDG_CURRENT_DESKTOP':'KDE'})[0], 'try')
        gio.SettingsSchemaSource.get_default.assert_not_called()

    def test_geoclue_missing(self):
        self.assertEqual(system_location_status(Mock(), False, {'XDG_CURRENT_DESKTOP':'KDE'})[0], 'unavailable')

    def test_geoclue_schema_missing_falls_back(self):
        gio = Mock()
        gio.SettingsSchemaSource.get_default.return_value.lookup.return_value = None
        self.assertEqual(system_location_status(gio, True, {'XDG_CURRENT_DESKTOP':'GNOME'})[0], 'try')

    def test_ip_offer_only_once_and_can_be_disabled(self):
        self.assertTrue(should_suggest_ip({'suggest_ip_fallback':True}, False))
        self.assertFalse(should_suggest_ip({'suggest_ip_fallback':True}, True))
        self.assertFalse(should_suggest_ip({'suggest_ip_fallback':False}, False))
        self.assertFalse(should_suggest_ip({'suggest_ip_fallback':True}, False, demo=True))

    def test_no_automatic_ip_network_on_failure(self):
        from pathlib import Path
        ui = (Path(__file__).resolve().parents[1] / 'aeroscope/ui.py').read_text()
        self.assertIn('self._suggest_ip_location', ui)
        self.assertIn('self._start_ip_lookup()', ui)
        self.assertIn('on_response=self._ip_suggestion_answer', ui)
        self.assertNotIn('GLib.timeout_add_seconds(2, self.confirm_ip_location)', ui)

if __name__=='__main__': unittest.main()
