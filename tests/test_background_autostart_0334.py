"""Login/autostart and regional interval regression checks, no GTK required."""
import os
from pathlib import Path
from unittest.mock import patch

from aeroscope import autostart, settings
from aeroscope.regional_poll import (INTERVALS, BACKGROUND_INTERVALS,
                                      describe_interval, regional_mode)

ROOT = Path(__file__).resolve().parents[1]


def test_interval_choices_defaults_and_labels():
    assert settings.DEFAULT['refresh'] == 10
    assert settings.DEFAULT['refresh_background'] == 10
    assert settings.DEFAULT['autostart_login'] is False
    assert INTERVALS == (10, 15, 20, 30, 45, 60, 120, 240, 480, 600)
    assert BACKGROUND_INTERVALS[0] == 0
    assert describe_interval(240) == '4 minutos'
    assert describe_interval(0).startswith('Desativado')


def test_regional_mode_for_main_pip_tray_login():
    base = dict(visible_seconds=30, background_seconds=120)
    assert regional_mode(started=False, main_visible=False, pip_visible=False, **base) == ('dormant', 0)
    assert regional_mode(started=True, main_visible=True, pip_visible=False, **base) == ('foreground', 30)
    assert regional_mode(started=True, main_visible=False, pip_visible=True, **base) == ('foreground', 30)
    assert regional_mode(started=True, main_visible=False, pip_visible=False, **base) == ('background', 120)
    assert regional_mode(started=True, main_visible=False, pip_visible=False,
                         visible_seconds=10, background_seconds=0) == ('paused', 0)


def test_autostart_xdg_write_read_remove(tmp_path):
    env = {'XDG_CONFIG_HOME': str(tmp_path)}
    with patch.dict(os.environ, env):
        assert not autostart.enabled()
        autostart.configure(True)
        entry = autostart.entry_path()
        assert entry == tmp_path / 'autostart' / autostart.ENTRY_NAME
        assert autostart.enabled()
        assert 'Exec=aeroscope --background' in entry.read_text('utf-8')
        assert 'TryExec=aeroscope' in entry.read_text('utf-8')
        autostart.configure(False)
        assert not autostart.enabled()
        assert not entry.exists()


def test_dont_delete_an_unrelated_autostart_entry(tmp_path):
    with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(tmp_path)}):
        entry = autostart.entry_path()
        entry.parent.mkdir(parents=True)
        entry.write_text('[Desktop Entry]\nType=Application\nExec=custom\n')
        autostart.configure(False)
        assert entry.exists()


def test_settings_upgrade_and_autostart_source_of_truth(tmp_path):
    with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(tmp_path)}):
        with patch.object(settings, 'CONFIG_DIR', tmp_path/'aeroscope'):
            settings.CONFIG_DIR.mkdir()
            (settings.CONFIG_DIR/'settings.json').write_text('{"refresh":120}', 'utf-8')
            loaded = settings.load()
            assert loaded['refresh'] == 120
            assert loaded['refresh_background'] == 10
            assert loaded['autostart_login'] is False
            autostart.configure(True)
            assert settings.load()['autostart_login'] is True
            loaded = settings.load()
            loaded['refresh_background'] = 0
            settings.save(loaded)
            assert settings.load()['refresh_background'] == 0


def test_main_wires_login_and_regional_modes_to_gtk():
    ui = (ROOT/'aeroscope/ui.py').read_text()
    prefs = (ROOT/'aeroscope/preferences.py').read_text()
    assert "background_start = '--background' in sys.argv" in ui
    assert 'def _autostart_tray_check(self):' in ui
    assert 'self._ensure_background_hold()' in ui
    assert 'GLib.timeout_add(1700, self.monitor_panel.start_initial_checks)' in ui
    assert 'self._regional_tracking_started = not getattr(app,' in ui
    assert 'def _effective_regional_mode(self):' in ui
    assert "elif key in ('refresh', 'refresh_background'):" in ui
    assert 'def _sync_regional_cadence(self):' in ui
    assert 'Start automatically at login' in prefs
    assert 'Regional refresh — tray only' in prefs
