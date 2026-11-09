"""Regression for historical callsign search; no API calls required."""
import ast
from pathlib import Path
from unittest.mock import patch
import pytest

from aeroscope import data
from aeroscope.search_suggestions import (
    classify_aircraft_identifier, historical_suggestions, grouped_suggestions,
)


def test_long_callsign_is_global_aircraft_search_not_city():
    assert classify_aircraft_identifier('ARCANJO9') == 'callsign'
    assert classify_aircraft_identifier('GLO1732') == 'callsign'
    assert classify_aircraft_identifier('PT-MUJ') == 'registration'
    assert classify_aircraft_identifier('E48DF5') == 'hex'
    assert classify_aircraft_identifier('São Paulo') is None


def test_historical_callsign_exact_not_prefix_collision():
    pages = [
        {'flights': [
            {'flight_id': 'a1b2c3:2026-11-06T16:00:00Z', 'icao24': 'a1b2c3', 'callsign': 'ARCANJO9',
             'start_ts': '2026-11-06T16:00:00Z', 'start_airport_ident': 'SBBH', 'end_airport_ident': 'SNDV'},
            {'flight_id': 'a1b2c4:2026-11-06T15:00:00Z', 'icao24': 'a1b2c4', 'callsign': 'ARCANJO90'},
        ], 'cursor': 'next'},
        {'flights': [
            {'flight_id': 'a1b2c3:2026-11-05T16:00:00Z', 'icao24': 'a1b2c3', 'callsign': 'ARCANJO9',
             'start_ts': '2026-11-05T16:00:00Z', 'registration': 'PR-ABC'},
        ], 'cursor': None},
    ]
    seen = []

    def fake_post(url, body, timeout=15):
        seen.append((url, body))
        return pages[len(seen)-1]

    with patch.object(data, '_post_json', side_effect=fake_post):
        result = data.search_historical_flights('callsign', 'ARCANJO9')
    assert len(result) == 2
    assert all(item['callsign'] == 'ARCANJO9' for item in result)
    assert seen[0][1]['match'] == {'callsign_prefix': 'ARCANJO9'}
    assert seen[0][1]['include_path'] is False
    assert 'start_from' in seen[0][1]
    assert seen[1][1]['cursor'] == 'next'

    suggestions = historical_suggestions('ARCANJO9', result)
    assert suggestions[0].kind == 'history'
    assert 'SBBH' in suggestions[0].subtitle
    groups = grouped_suggestions(suggestions)
    assert groups[0][0] == 'history'


def test_hex_and_registration_search_and_validation():
    with patch.object(data, '_post_json', return_value={'flights': [], 'cursor': None}) as call:
        assert data.search_historical_flights('hex', 'e48df5') == []
        assert call.call_args.args[1]['match'] == {'icao24': ['e48df5']}
        assert data.search_historical_flights('registration', 'PT-MUJ') == []
        assert call.call_args.args[1]['match'] == {'registration_prefix': 'PT-MUJ'}
    with pytest.raises(ValueError):
        data.search_historical_flights('callsign', 'x')


def test_ui_contains_on_demand_archive_workflow():
    src = (Path(__file__).resolve().parents[1] / 'aeroscope' / 'ui.py').read_text()
    tree = ast.parse(src)
    win = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'RadarWindow')
    methods = {x.name: x for x in win.body if isinstance(x, ast.FunctionDef)}
    assert '_start_historical_search' in methods
    assert '_activate_historical_flight' in methods
    snippet = ast.get_source_segment(src, methods['_search_changed'])
    assert 'search_historical_flights' not in snippet
    # Historic selections go straight to the established replay path.
    assert 'self.show_historical_track(flight_id)' in ast.get_source_segment(src, methods['_activate_historical_flight'])
