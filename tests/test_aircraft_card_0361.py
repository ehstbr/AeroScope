"""Telemetry card 0.3.62: ADS-B facts, missing data and UI wiring."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aeroscope.aircraft_card_data import (snapshot, heading_label, source_label,
                                         speed_label, vertical_rate_label)
from aeroscope.data import Aircraft
from aeroscope.i18n import LANGUAGE

ROOT = Path(__file__).resolve().parents[1]


def make_plane(**updates):
    args = dict(hex='e498c8', flight='AZU1234', registration='PS-BVP',
                model='E295', lat=-20.1367, lon=-44.8839,
                altitude_ft=25500, speed_kts=405, track=265,
                vertical_rate=-640, seen=2, source='adsb_icao',
                squawk='2000', emergency='', on_ground=False)
    args.update(updates)
    return Aircraft(**args)


def test_snapshot_has_flight_identifiers_and_six_metrics():
    facts = snapshot(make_plane())
    assert facts['flight'] == 'AZU1234'
    assert facts['registration'] == 'PS-BVP'
    assert 'Embraer' in facts['model']
    assert facts['icao24'] == 'E498C8'
    assert facts['altitude'] == ('25.500 ft' if LANGUAGE == 'pt_BR' else '25,500 ft')
    assert facts['speed'] == '750 km/h'
    assert facts['vertical_rate'] == '↓ 640 ft/min'
    assert facts['heading'] == '265° W'
    assert facts['source'] == 'ADS-B'
    assert facts['squawk'] == '2000'
    assert facts['position'] == '-20.1367, -44.8839'
    assert facts['alert'] == ''


@pytest.mark.parametrize('unit,expected', [('kmh', '750 km/h'),
                                           ('kt', '405 kt'),
                                           ('mph', '466 mph')])
def test_speed_respects_preference(unit, expected):
    assert snapshot(make_plane(), unit)['speed'] == expected


def test_vertical_rate_and_heading_do_not_infer_values():
    assert vertical_rate_label(900) == '↑ 900 ft/min'
    assert vertical_rate_label(-1100) == ('↓ 1.100 ft/min' if LANGUAGE == 'pt_BR' else '↓ 1,100 ft/min')
    assert vertical_rate_label(0).endswith('0 ft/min')
    assert vertical_rate_label(None) == '—'
    assert heading_label(0) == '000° N'
    assert heading_label(360) == '000° N'
    assert heading_label(45) == '045° NE'
    assert heading_label(None) == '—'
    assert speed_label(None) == '—'


def test_no_invented_ground_status_and_missing_aircraft_fields():
    facts = snapshot(make_plane(flight='', registration='', model='',
                                altitude_ft=None, speed_kts=None,
                                vertical_rate=None, squawk='',
                                source='', on_ground=None))
    assert facts['flight'] and facts['registration']
    assert facts['altitude'] == '—'
    assert facts['speed'] == '—'
    assert facts['squawk'] == '—'
    assert facts['vertical_rate'] == '—'
    assert facts['source']
    assert snapshot(make_plane(altitude_ft=None, on_ground=True))['altitude'] != '—'


def test_transponder_priority_only_for_actual_indicators():
    assert snapshot(make_plane(squawk='7700'))['alert_level'] == 'critical'
    assert snapshot(make_plane(squawk='7600'))['alert_level'] == 'warning'
    assert snapshot(make_plane(squawk='7500'))['alert_level'] == 'critical'
    assert snapshot(make_plane(squawk='2000'))['alert_level'] == 'none'
    assert source_label('mlat') == 'MLAT'
    assert source_label('tisb_icao') == 'TIS-B'


def test_widget_uses_compact_grid_no_history_and_existing_follow_controls():
    src = (ROOT / 'aeroscope/aircraft_widget.py').read_text()
    ast.parse(src)
    # Regression for the GTK intrinsic image-size issue: the widget itself
    # must never contain a Gtk.Picture or a button wrapping a full-size image.
    assert 'Gtk.Picture' not in src.replace('A Gtk.Picture', '')
    assert 'self.picture' not in src
    assert 'self.photo_column' not in src
    assert 'self.photo_button.set_visible(False)' in src
    assert 'self.photo_button.set_tooltip_text(' in src
    assert 'self.photo_button.connect(\'clicked\', self._open_photo)' in src
    assert 'self.set_size_request(310, -1)' in src
    assert 'self.metric_values' in src
    assert 'Gtk.Grid(column_spacing=12, row_spacing=6)' in src
    assert "self.controller.radar.settings.get('speed', 'kmh')" in src
    assert 'self.controller.center_aircraft(self.code)' in src
    assert 'self.controller.toggle_aircraft_follow(self.code)' in src
    assert 'fetch_history' not in src
    assert 'routeset' not in src
