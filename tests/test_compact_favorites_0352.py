"""0.3.52: concise Favorites weather and a non-redundant airport context menu."""
from __future__ import annotations

import ast
from pathlib import Path

from aeroscope.airport_weather_badge import metar_badge
from aeroscope.weather_data import Metar

ROOT = Path(__file__).resolve().parents[1]


def test_approved_categories_are_displayed_without_interpreting_raw_bulletins():
    for category in ('VFR', 'MVFR', 'IFR', 'LIFR'):
        report = Metar('SBBH', -19.85, -43.95, 'METAR SBBH TEST', category,
                       '09/11/2026 13:00 UTC', {})
        assert metar_badge(report) == category
    # If NOAA doesn't provide the flight category, don't fabricate one.
    report = Metar('SBBH', -19.85, -43.95, 'METAR SBBH TEST', '', '', {})
    assert metar_badge(report) == 'METAR'
    no_report = Metar('SBBH', -19.85, -43.95, '', '', '', {})
    assert metar_badge(no_report) is None


def test_favorites_render_a_compact_category_without_raw_metar():
    ui = (ROOT / 'aeroscope/monitor_ui.py').read_text()
    ast.parse(ui)
    card = ui.split('    def _render_metar_favorite(', 1)[1].split('\n    def ', 1)[0]
    assert 'category = metar_badge(report)' in card
    assert "badge.add_css_class('metar-' + category.lower())" in card
    assert 'info.append(raw)' not in card
    assert 'report.raw' not in card
    assert "_('Observed: {value0}')" in card
    assert "self.radar.select_airport(airport)" in card
    assert "self.radar.select_weather_station(m)" in card
    assert "info.add_controller(inspect_click)" in card
    assert "locate.connect('clicked'" in card
    assert "remove.connect('clicked'" in card


def test_airport_context_menu_is_not_redundant():
    ui = (ROOT / 'aeroscope/ui.py').read_text()
    ast.parse(ui)
    menu = ui.split('    def show_airport_context_menu(', 1)[1].split('\n    def ', 1)[0]
    assert 'self.select_airport(iata)' in menu  # right-click already selects
    assert "item(_('Open airport details')" not in menu
    assert "item(_('Center airport on map')" in menu
    assert "_('Add airport to favorites')" in menu
    assert "_('Remove airport from favorites')" in menu
