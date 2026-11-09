"""SIGMET performance and geometry regressions, without GTK or NOAA access."""
from __future__ import annotations
import math
from pathlib import Path

from aeroscope.sigmet_geometry import (
    project, simplify_path, prepare_sigmets, viewport_bounds,
    scene_visible, overlaps,
)
from aeroscope.sigmet_readable import sigmet_label_point, sigmet_at_point
from aeroscope.weather_data import Sigmet

ROOT = Path(__file__).resolve().parents[1]


def circle(lat, lon, radius=0.6, count=240):
    return tuple((lat + radius * math.sin(i * math.tau / count),
                  lon + radius * math.cos(i * math.tau / count))
                 for i in range(count))


def sigmet(name, lat, lon, count=240):
    return Sigmet(name, (circle(lat, lon, count=count),), name, {'hazard':name})


def test_projection_matches_mercator_and_bounds():
    assert project(0, 0) == (0.5, 0.5)
    assert abs(project(45, 0)[1] - .359725) < .0001
    assert overlaps((.2, .2, .4, .4), (.39, .39, .6, .6))
    assert not overlaps((.1, .1, .2, .2), (.5, .5, .8, .8))


def test_one_geometry_scene_reused_across_map_views():
    advisories = [sigmet('TS', -19, -44), sigmet('ICE', -2, -22)]
    scene = prepare_sigmets(advisories, sigmet_label_point)
    assert len(scene) == 2
    assert scene[0].advisory is advisories[0]
    assert scene[0].marker is not None
    # Discard offscreen advisory without losing data/hit-test detail.
    x, y = project(-19, -44)
    near = viewport_bounds(x, y, 640, 420, 256 * 2 ** 8)
    assert [entry[0].advisory for entry in scene_visible(scene, near)] == [advisories[0]]
    assert sigmet_at_point(advisories, *scene[1].marker) is advisories[1]


def test_zoom_simplification_and_cache_without_touching_original():
    advisory = sigmet('TS', -19, -44, count=850)
    original = advisory.rings[0]
    ring = prepare_sigmets([advisory])[0].rings[0]
    low = ring.at_zoom(4)
    assert 4 <= len(low) < len(original) / 4
    assert low is ring.at_zoom(4.8)  # cached for fractional zoom changes
    assert ring.at_zoom(12) != low
    assert advisory.rings[0] == original
    assert len(ring._cache) == 2


def test_all_advisories_retained_but_culling_only_draws_nearby():
    advisories = [sigmet('TS', -30+i*.12, -58+i*.12, count=120) for i in range(150)]
    scene = prepare_sigmets(advisories)
    assert len(scene) == 150  # no arbitrary 65 SIGMET limit
    x, y = project(-19.8, -44.0)
    visible = scene_visible(scene, viewport_bounds(x, y, 750, 550, 256*2**8))
    assert len(visible) < 15
    rendered = sum(len(r.at_zoom(5)) for _s, rings in visible for r,_shift in rings)
    assert rendered < sum(len(r) for item in advisories for r in item.rings)


def test_antimeridian_shape_is_not_projected_across_the_world():
    advisory = Sigmet('TS', (((14, 179.5), (14, -179.5), (15, -179.5),
                              (15, 179.5), (14, 179.5)),), 'TS')
    scene = prepare_sigmets([advisory])
    assert len(scene) == 1
    assert scene[0].bbox[2] - scene[0].bbox[0] < .02
    cx, cy = project(14.5, -179.8)
    assert len(scene_visible(scene, viewport_bounds(cx, cy, 640, 400, 256 * 2**7))) == 1


def test_single_cached_cairo_canvas_instead_of_per_polygon_path_layers():
    code = (ROOT / 'aeroscope' / 'weather_ui.py').read_text()
    ui = (ROOT / 'aeroscope' / 'ui.py').read_text()
    assert 'self.sigmet_canvas = Gtk.DrawingArea()' in code
    assert 'self.sigmet_canvas.set_can_target(False)' in code
    assert 'cr.new_path()' in code and 'cr.stroke()' in code
    assert 'Shumate.PathLayer.new' not in code
    assert 'sigmets[:65]' not in code
    assert 'self.weather.sigmet_at_location(lat, lon)' in ui
    assert "GLib.timeout_add(240, self._sync_symbols)" in code


def test_noaa_refresh_reuses_unchanged_contours_and_zoom_caches():
    first = sigmet('TS', -19, -44)
    old = prepare_sigmets([first])
    cached = old[0].rings[0].at_zoom(5)
    newer_same = Sigmet('TS', first.rings, 'TS', {'hazard':'TS'})
    new = prepare_sigmets([newer_same], previous=old)
    assert new[0] is old[0]  # no redraw required
    assert new[0].rings[0].at_zoom(5) is cached
    updated = Sigmet('TS', first.rings, 'UPDATED BULLETIN', {'hazard':'TS'})
    edited = prepare_sigmets([updated], previous=new)
    assert edited[0] is not old[0]
    assert edited[0].rings[0] is old[0].rings[0]  # geometry survives
    assert edited[0].advisory is updated


def test_an_open_polygon_boundary_stays_closed_in_cairo():
    text = (ROOT / 'aeroscope' / 'weather_ui.py').read_text()
    assert 'cr.close_path()' in text
