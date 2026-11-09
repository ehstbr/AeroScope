"""v0.3.24 regressions for fixed clock and immediate return to smooth live mode."""
from pathlib import Path
import math
from aeroscope.tower_radar import clock_ring_radius, ring_label_anchor, full_map_radius
from aeroscope.motion import PositionTransition

ROOT = Path(__file__).resolve().parents[1]


def test_clock_radius_never_depends_on_aircraft_position():
    width, height = 1280, 900
    radii = {clock_ring_radius(width,height,x,y)
             for x,y in [(0,0),(2,200),(width/2,height/2),(width-3,height-1)]}
    assert radii == {168.0}


def test_ring_labels_remain_on_their_circles():
    w,h=1280,900
    cx,cy=w/2,h/2
    radius=full_map_radius(w,h,cx,cy)*.88
    for part in (.25,.5,.75,1.0):
        r=radius*part
        result=ring_label_anchor(cx,cy,r,w,h,68)
        assert result is not None
        x,y=result
        # Anchor is top left of a 68px wide, 18px high label whose center
        # is 11 pixels below y; exactly on the circle, not floating.
        d=math.hypot((x+34)-cx,(y+11)-cy)
        assert abs(d-r) < 1.1


def test_no_label_when_circle_has_no_visible_arc():
    assert ring_label_anchor(500,500,1000,600,500,80) is None


def test_turning_off_sweep_reconnects_normal_animation_without_api():
    src=(ROOT/'aeroscope/ui.py').read_text()
    assert 'self._resume_live_positions_after_sweep()' in src
    section=src.split('def _resume_live_positions_after_sweep(self):',1)[1].split('def _tower_sweep_tick(self):',1)[0]
    assert 'for hexid, virtual in tuple(self._sweep_virtual.items()):' in section
    assert 'virtual.duration - (now - virtual.started_at)' in section
    assert 'self._sweep_pending.clear()' in section
    assert 'self._start_animation_timer()' in section
    assert 'fetch_' not in section
    assert 'for degrees in range(0, 360, 30)' not in src.split('def _draw_radar',1)[1].split('def show_preferences',1)[0]


def test_clock_is_not_centered_on_map_or_reused_after_deselection():
    source = (ROOT / 'aeroscope/ui.py').read_text()
    section = source.split('def _selected_tower_reference(self, width, height):',1)[1].split('def _draw_relative_clock',1)[0]
    assert 'self.markers.get(self.selected_hex)' in section
    assert 'marker.marker.get_latitude()' in section
    assert 'marker.marker.get_longitude()' in section
    paint = source.split('def _draw_relative_clock(self, cr, width, height):',1)[1].split('def _draw_radar(',1)[0]
    assert 'cx, cy, heading = reference' in paint
    assert 'clock_ring_radius(width, height, cx, cy)' in paint
    clear = source.split('def _clear_selected(self):',1)[1].split('def _follow_changed',1)[0]
    assert 'self.clock_decoration.queue_draw()' in clear
