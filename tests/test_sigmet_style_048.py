"""Regression suite for the SIGMET visual palette, opacity and fast renderer."""
from pathlib import Path

import pytest

from aeroscope.weather_data import Sigmet
from aeroscope.settings import DEFAULT
from aeroscope.sigmet_geometry import prepare_sigmets
from aeroscope.sigmet_style import (COLORS, LEGACY, classify_sigmet, display_style,
                                    sigmet_alpha)

ROOT = Path(__file__).resolve().parents[1]
RECT = (((-19.0, -44.0), (-19.0, -43.0), (-18.0, -43.0), (-18.0, -44.0)),)


def report(hazard, raw='', metadata=None):
    return Sigmet(hazard, RECT, raw or hazard, metadata or {'hazard': hazard})


@pytest.mark.parametrize('hazard,expected', [
    ('TS', 'storm'), ('TURB', 'turbulence'), ('ICE', 'icing'),
    ('VA', 'volcanic'), ('TC', 'cyclone'), ('MTW', 'mountain'),
    ('DS', 'dust'), ('SS', 'dust'), ('RDOACT', 'radioactive'),
    ('SIGMET', 'generic'),
])
def test_hazard_color_matches_portuguese_description(hazard, expected):
    assert classify_sigmet(report(hazard)).key == expected


def test_metadata_takes_priority_over_ambiguous_bulletin():
    # Only the observation's explicit hazard should decide the palette.
    advisory = report('SIGMET', 'ICE SEV; TS OBS', {'phenomenon': 'ICE'})
    assert classify_sigmet(advisory).key == 'icing'
    assert classify_sigmet(report('SIGMET', 'UNKNOWN')).key == 'generic'


def test_contour_and_badge_share_the_same_palette_instance():
    r = report('ICE')
    shape = prepare_sigmets([r])[0]
    assert shape.style is COLORS['icing']
    assert display_style(shape.style, True) is shape.style
    assert display_style(shape.style, False) is LEGACY
    assert COLORS['icing'].rgb != COLORS['storm'].rgb


def test_noaa_updates_preserve_cached_geometry_and_update_color():
    ice = report('ICE')
    first = prepare_sigmets([ice])
    cached = first[0].rings[0].at_zoom(7)
    change = Sigmet('TS', ice.rings, 'TS OBS', {'hazard': 'TS'})
    second = prepare_sigmets([change], previous=first)
    assert second[0].rings[0] is first[0].rings[0]
    assert second[0].rings[0].at_zoom(7) is cached
    assert second[0].style.key == 'storm'
    assert first[0].style.key == 'icing'


def test_fill_opacity_and_selected_state():
    assert sigmet_alpha(False, False) == (.10, .72)
    assert sigmet_alpha(True, False) == (.18, .96)
    assert sigmet_alpha(False, True) == (.065, .72)
    assert sigmet_alpha(True, True) == pytest.approx((.117, .96))
    assert sigmet_alpha(True, True, filled=False) == (0.0, .96)


def test_new_prefs_are_enabled_by_default_and_shared():
    assert DEFAULT['sigmet_fill'] is True
    assert DEFAULT['sigmet_colors'] is True
    prefs = (ROOT / 'aeroscope/preferences.py').read_text()
    ui = (ROOT / 'aeroscope/ui.py').read_text()
    assert 'Show SIGMET area fill' in prefs
    assert 'Use colors by SIGMET phenomenon' in prefs
    assert 'self.weather.presentation_changed(key)' in ui
    assert "key in ('sigmet_fill', 'sigmet_colors')" in ui


def test_one_canvas_and_no_new_network_poll_on_presentation_change():
    code = (ROOT / 'aeroscope/weather_ui.py').read_text()
    assert 'self.sigmet_canvas = Gtk.DrawingArea()' in code
    assert 'cr.fill_preserve()' in code
    assert 'cr.stroke()' in code
    assert 'shape.style' in code
    assert "selected_advisory = getattr(self.manager.radar, 'selected_sigmet', None)" in code
    assert 'cr.new_path()' in code
    fn = code.split('def presentation_changed(self, key):', 1)[1].split('def region_updated', 1)[0]
    assert 'queue_draw()' in fn
    assert 'self.tick()' not in fn and 'fetch_noaa' not in fn
    assert 'self._next_noaa = 0.0' not in fn


def test_palette_has_unique_safe_css_selectors_and_font_color():
    css = (ROOT / 'assets/style.css').read_text()
    assert len({style.rgb for style in COLORS.values()}) == len(COLORS)
    for key, style in COLORS.items():
        assert style.key == key
        assert f'.sigmet-{key} ' in css
    assert '.sigmet-legacy ' in css
    assert 'color: #fff' in css
