"""Regression coverage for registration / ICAO24 marker captions and header."""
from dataclasses import dataclass
from pathlib import Path
import ast

from aeroscope.marker_labels import aircraft_marker_caption
from aeroscope.settings import DEFAULT

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Plane:
    registration: str | None = 'PR-YJF'
    hex: str = 'E4962F'
    flight: str = 'AZU2876'


def test_caption_mode_off_default():
    assert DEFAULT['marker_label'] == 'off'
    assert aircraft_marker_caption(Plane(), 'off') == ''


def test_registration_and_icao_modes():
    assert aircraft_marker_caption(Plane(), 'registration') == 'PR-YJF'
    assert aircraft_marker_caption(Plane(), 'icao') == 'E4962F'
    assert aircraft_marker_caption(Plane(registration=None), 'registration') == 'E4962F'


def test_unknown_or_bad_label_is_safe_and_not_callsign():
    plane = Plane(registration='   ', hex='ab12cd', flight='ANV123')
    assert aircraft_marker_caption(plane, 'registration') == 'AB12CD'
    assert aircraft_marker_caption(Plane(registration=''), 'not-a-mode') == ''
    assert aircraft_marker_caption(Plane(registration='AA\nBB'), 'registration') == 'AABB'


def test_marker_caption_follow_updates_and_pip():
    ui = (ROOT/'aeroscope'/'ui.py').read_text()
    pip = (ROOT/'aeroscope'/'mini_map.py').read_text()
    preferences = (ROOT/'aeroscope'/'preferences.py').read_text()
    ast.parse(ui)
    ast.parse(pip)
    assert 'marker.set_label_mode(value)' in ui
    assert "label_mode=self.settings['marker_label']" in ui
    assert "label_mode=self.radar.settings['marker_label']" in pip
    assert 'set_label_mode(self.radar.settings' in pip
    assert 'Labels next to aircraft icons' in preferences
    # Marker location is unchanged; only its draw area grows for the caption.
    assert 'self.area.set_content_width(100 if mode !=' in ui
    assert 'self.marker.set_location(' in ui


def test_header_location_is_not_duplicated():
    ui = (ROOT/'aeroscope'/'ui.py').read_text()
    assert 'header.pack_start(location_menu)' not in ui
    assert 'self.simple_map.set_show_zoom_buttons(False)' in ui
    assert "header.pack_end(icon_button('view-refresh-symbolic'" in ui
    assert "('location-ip', self._ip_location)" in ui
