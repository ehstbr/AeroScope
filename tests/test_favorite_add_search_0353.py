"""Regression tests for 0.3.53 unified add-to-favorites search and menu lifetime."""
from pathlib import Path
from types import SimpleNamespace

from aeroscope.data import AIRPORTS
from aeroscope.favorite_search import favorite_candidates
from aeroscope.weather_data import Metar

ROOT = Path(__file__).resolve().parents[1]


def plane(hexid='e48a01', registration='PR-XYZ', flight='GLO1234', model='B738'):
    return SimpleNamespace(hex=hexid, registration=registration, flight=flight,
                           model=model, lat=-20., lon=-44.)


def station(code):
    return Metar(code, -20.19, -44.87, 'METAR ' + code, 'VFR', '10:00 UTC', {})


def test_favorites_search_airport_icao_iata_and_accent_insensitive_name():
    airport_iata = favorite_candidates('CNF', [], AIRPORTS, [])
    airport_icao = favorite_candidates('SBCF', [], AIRPORTS, [])
    airport_name = favorite_candidates('divinopolis', [], AIRPORTS, [])
    assert airport_iata[0].kind == airport_icao[0].kind == 'airport'
    assert airport_iata[0].key == airport_icao[0].key == 'CNF'
    assert any(a.key == 'DIQ' and a.kind == 'airport' for a in airport_name)


def test_favorites_search_aircraft_identifier_and_station_no_duplicated_airport():
    matches = favorite_candidates('PR-XYZ', [plane()], AIRPORTS, [])
    assert matches[0].kind == 'aircraft' and matches[0].aircraft_kind == 'registration'
    assert matches[0].key == 'PR-XYZ'
    matches = favorite_candidates('E48A01', [plane(registration='')], AIRPORTS, [])
    assert matches[0].aircraft_kind == 'icao'
    matches = favorite_candidates('KJNB', [], AIRPORTS, [station('KJNB')])
    assert [m.kind for m in matches] == ['station']
    assert matches[0].lat == -20.19
    matches = favorite_candidates('SBBH', [], AIRPORTS, [station('SBBH')])
    assert [m.kind for m in matches] == ['airport']


def test_favorites_search_does_not_query_network_or_generate_unknown_result():
    assert favorite_candidates('NOT-AN-AIRPORT', [], AIRPORTS, []) == []
    assert favorite_candidates('', [plane()], AIRPORTS, [station('KJNB')]) == []
    assert favorite_candidates('SB', [], AIRPORTS, [station('KJNB')], per_kind=2)


def test_favorites_add_panel_offers_both_local_results_and_explicit_noaa_lookup():
    source = (ROOT / 'aeroscope/monitor_ui.py').read_text()
    assert "self.add_entry.connect('changed', self._search_favorites_changed)" in source
    assert 'favorite_candidates(query, self.radar.records.values(), AIRPORTS,' in source
    assert 'fetch_metar_station(term)' in source
    assert 'self.radar._toggle_airport_favorite(candidate.key)' in source
    assert 'self.radar._toggle_station_favorite(report)' in source
    assert 'self._add_candidate(candidate)' in source
    assert 'GLib.idle_add(\n                self._select_candidate_idle, match)' in source


def test_context_popover_unparents_after_gtk_event_and_marker_action_is_deferred():
    source = (ROOT / 'aeroscope/ui.py').read_text()
    assert "popover.connect('closed', lambda p: p.unparent())" not in source
    assert source.count('protect_context_menu(popover, widget, GLib.idle_add, self._detach_context_popover)') == 3
    assert source.count('self._activate_context_action(popover,') == 3
    assert 'GLib.idle_add(perform)' in source
