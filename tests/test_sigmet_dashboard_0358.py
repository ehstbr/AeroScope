"""0.3.58: location SIGMET coverage and slim UTC validity timelines."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from aeroscope.sigmet_nearby import (currently_valid, region_key, region_bbox,
                                      sigmets_covering)
from aeroscope.validity_time import (validity_window, elapsed_fraction,
                                     format_endpoint, parse_time)
from aeroscope.weather_data import Sigmet, Metar

ROOT = Path(__file__).resolve().parents[1]


def warning(meta=None, name='TS', lat=-20., lon=-44.):
    return Sigmet(name, (((lat - 1, lon - 1), (lat - 1, lon + 1),
                          (lat + 1, lon + 1), (lat + 1, lon - 1)),),
                  'EMBD TS FCST FL200', meta or {})


def stamp(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()


def test_only_overlapping_valid_sigmets_are_reported():
    now = stamp('2026-11-09T13:00:00Z')
    dates = {'validTimeFrom': '2026-11-09T12:00:00Z',
             'validTimeTo': '2026-11-09T14:00:00Z'}
    inside = warning(dates)
    distant = warning(dates, 'ICE', -4, -30)
    expired = warning({'validFrom': '2026-11-09T08:00:00Z',
                       'validTo': '2026-11-09T10:00:00Z'})
    assert sigmets_covering([inside, distant, expired], -20, -44, now=now) == (inside,)
    assert sigmets_covering([inside], -23, -44, now=now) == ()
    assert sigmets_covering([inside, inside], -20, -44, now=now) == (inside,)
    assert sigmets_covering([inside], float('nan'), -44, now=now) == ()
    assert currently_valid(inside, now=stamp('2026-11-09T15:00:00Z')) is False


def test_a_station_without_metar_can_still_have_sigmet():
    station = Metar('SNDV', -20.0, -44.0, '', 'N/D', '', {})
    matching = sigmets_covering([warning({'validTimeTo': '2099-01-01T00:00:00Z'})],
                                station.lat, station.lon)
    assert len(matching) == 1
    assert station.category == 'N/D'  # SIGMET never invents VFR/IFR.
    assert region_key(station.lat, station.lon) == region_key(-20.1, -43.9)
    south, west, north, east = region_bbox(region_key(-20, -44))
    assert south <= station.lat <= north and west <= station.lon <= east


def test_validity_progress_has_utc_dates_and_clamps():
    start = stamp('2026-11-09T23:00:00Z')
    end = stamp('2026-11-10T03:00:00Z')
    assert validity_window({'validFrom': start, 'validTo': end}) == (start, end)
    assert validity_window({'startTime': start * 1000, 'endTime': end * 1000}) == (start, end)
    assert validity_window({'validStart': str(int(start)), 'validEnd': str(int(end))}) == (start, end)
    assert elapsed_fraction(start, end, now=start - 100) == 0
    assert elapsed_fraction(start, end, now=start + 3600) == .25
    assert elapsed_fraction(start, end, now=end + 100) == 1
    assert format_endpoint(start) == '09/11 23:00'
    assert format_endpoint(end, full=True) == '10/11/2026 03:00 UTC'


def test_unknown_or_reversed_validity_never_produces_a_timeline():
    assert validity_window({}) is None
    assert validity_window({'validFrom': 'bad date', 'validTo': '2026-11-09T13:00:00Z'}) is None
    assert validity_window({'validFrom': '2026-11-09T14:00:00Z',
                            'validTo': '2026-11-09T13:00:00Z'}) is None
    assert validity_window(None) is None
    assert elapsed_fraction(10, 10) is None
    assert parse_time('') is None


def test_details_favorites_and_floating_widgets_integrate_independently():
    ui = (ROOT / 'aeroscope/ui.py').read_text()
    weather = (ROOT / 'aeroscope/weather_ui.py').read_text()
    monitor = (ROOT / 'aeroscope/monitor_ui.py').read_text()
    floating = (ROOT / 'aeroscope/floating_widget.py').read_text()
    component = (ROOT / 'aeroscope/validity_widget.py').read_text()
    assert 'self._append_location_sigmet(metar.lat, metar.lon)' in ui
    assert 'self._append_location_sigmet(lat, lon)' in ui
    assert ui.count('sigmet_timeline(advisory)') == 2
    assert 'self._queue_sigmet_targets()' in weather
    assert "sigmets_covering(bulletins, lat, lon)" in weather
    assert 'weather.sigmet_coverage(*position)' in monitor
    assert 'card.update_sigmets(advisories, sigmet_state)' in (ROOT / 'aeroscope/dashboard.py').read_text()
    assert 'self.sigmet_chip.set_visible(bool(advisories))' in floating
    assert 'sigmet_timeline(advisory)' in floating
    assert 'GLib.timeout_add_seconds(60, self._tick)' in component
    assert 'self.progress.set_fraction(fraction)' in component
    assert 'sigmet-validity-track trough' in (ROOT / 'assets/style.css').read_text()
