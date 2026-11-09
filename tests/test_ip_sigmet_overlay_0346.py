"""Regressions for explicit GeoClue retries and map NOAA status cleanup."""
from pathlib import Path
import ast
from aeroscope.location_policy import should_suggest_ip

ROOT = Path(__file__).resolve().parents[1]


def test_now_not_later_can_be_repeated_by_user():
    settings = {'suggest_ip_fallback': True}
    assert should_suggest_ip(settings, already_offered=False)
    assert not should_suggest_ip(settings, already_offered=True)
    assert should_suggest_ip(settings, already_offered=True, user_initiated=True)
    assert not should_suggest_ip({'suggest_ip_fallback': False}, True, user_initiated=True)
    assert not should_suggest_ip(settings, True, demo=True, user_initiated=True)


def test_manual_location_calls_dialog_again_but_startup_respects_once():
    text = (ROOT/'aeroscope/ui.py').read_text()
    ast.parse(text)
    assert 'self.locate(user_initiated=False)' in text
    assert 'def locate(self, *_args, force=False, user_initiated=True):' in text
    assert 'self._suggest_ip_location(reason, user_initiated=user_initiated)' in text
    assert 'user_initiated=self._location_request_manual' in text
    assert "self.settings['suggest_ip_fallback'] = False" in text
    # Single permission dialog remains: explicit IP consent precedes HTTP.
    assert 'on_response=self._ip_suggestion_answer' in text


def test_no_floating_sigmet_or_metar_status():
    text = (ROOT/'aeroscope/weather_ui.py').read_text()
    ast.parse(text)
    assert 'overlay.add_overlay(self.status)' not in text
    assert 'self.status.set_text(' not in text
    assert 'self._show_sigmet' in text
    assert 'self._show_metar' in text
