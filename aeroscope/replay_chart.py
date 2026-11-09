"""Cairo flight telemetry chart for the native GNOME history player.

Uses the historical samples only; missing altitude/ground-speed is not
inferred, and independent ADS-B coverage segments never get connected.
"""
from __future__ import annotations
import datetime as dt
import math

AXES = ('clock', 'elapsed', 'distance')


def fraction_for_time(replay, timestamp, axis='clock'):
    if not replay or replay.duration <= 0:
        return 0.0
    if axis == 'distance':
        return min(1., max(0., replay.distance_at(timestamp) /
                           max(.001, replay.total_distance_km)))
    return min(1., max(0., (timestamp-replay.start)/replay.duration))


def time_for_fraction(replay, fraction, axis='clock'):
    fraction = min(1., max(0., float(fraction)))
    if axis == 'distance' and replay.total_distance_km > .01:
        return replay.time_at_distance(replay.total_distance_km * fraction)
    return replay.start + replay.duration * fraction


def x_label(replay, fraction, axis):
    fraction = min(1., max(0., fraction))
    if axis == 'distance':
        return f'{round(replay.total_distance_km * fraction)} km'
    elapsed = replay.duration * fraction
    if axis == 'elapsed':
        hours = int(elapsed // 3600)
        return f'{hours:02d}:{int((elapsed % 3600)//60):02d}'
    when = dt.datetime.fromtimestamp(replay.start + elapsed, dt.timezone.utc)
    return when.strftime('%H:%M')


def metric_bounds(replay, metric):
    values = [v for segment in replay.series(metric) for _, v in segment]
    if not values:
        return None
    lo, hi = min(values), max(values)
    if metric == 'altitude':
        lo = min(0, math.floor(lo / 1000) * 1000)
        hi = max(lo + 1000, math.ceil(hi / 1000) * 1000)
    else:
        lo = min(0, math.floor(lo / 50) * 50)
        hi = max(lo + 50, math.ceil(hi / 50) * 50)
    return lo, hi


def plot_chart(replay, cr, width, height, timestamp, *, axis='clock',
               altitude=True, speed=True, dark=False):
    """Draw both complete histories and a cursor for the current replay time.

    This is called from Gtk.DrawingArea.set_draw_func only. No Gtk widgets are
    mutated during painting, per GTK4's drawing contract.
    """
    width, height = max(1, width), max(1, height)
    left, right, top, bottom = 58., 54., 24., 34.
    w, h = max(1., width-left-right), max(1., height-top-bottom)
    fg = (.91, .94, .98) if dark else (.17, .22, .27)
    grid = (.59, .68, .75) if dark else (.30, .39, .46)

    cr.save()
    # Subtle grid, with enough room for a left and right numeric axis.
    for i in range(5):
        y = top + (h*i)/4
        cr.set_source_rgba(*grid, .17)
        cr.set_line_width(1)
        cr.move_to(left, y)
        cr.line_to(left+w, y)
        cr.stroke()
    for i in range(5):
        x = left + w*i/4
        cr.set_source_rgba(*grid, .10)
        cr.move_to(x, top)
        cr.line_to(x, top+h)
        cr.stroke()
        cr.set_source_rgba(*fg, .77)
        cr.select_font_face('Sans', 0, 0)
        cr.set_font_size(10)
        label = x_label(replay, i/4, axis)
        ext = cr.text_extents(label)
        cr.move_to(max(2, min(width-ext.width-2, x-ext.width/2)), top+h+18)
        cr.show_text(label)

    configurations = (
        ('altitude', altitude, (0.33, .67, .98), left-8, 'ft', False),
        ('speed', speed, (1., .66, .30), left+w+8, 'kt', True),
    )
    for metric, visible, color, axis_x, suffix, right_axis in configurations:
        if not visible:
            continue
        bounds = metric_bounds(replay, metric)
        if bounds is None:
            continue
        low, high = bounds
        for i in range(5):
            value = high - (high-low)*i/4
            label = f'{value:,.0f}'.replace(',', '.')
            if i == 0:
                label += ' ' + suffix
            cr.set_source_rgba(*color, .95)
            cr.set_font_size(9.5)
            ext = cr.text_extents(label)
            cr.move_to(axis_x + (4 if right_axis else -ext.width), top+h*i/4+3)
            cr.show_text(label)
        cr.set_source_rgba(*color, .96)
        cr.set_line_width(1.9)
        cr.set_line_join(1)
        for segment in replay.series(metric):
            if len(segment) < 2:
                continue
            # Avoid overpainting the chart for very long history tracks.
            # Every drawing stride is local to one segment: no fictitious gap.
            stride = max(1, (len(segment)-1)//max(1, round(w*2)))
            pts = segment[::stride]
            if pts[-1] is not segment[-1]:
                pts = pts + [segment[-1]]
            for j, (t, val) in enumerate(pts):
                x = left + w*fraction_for_time(replay, t, axis)
                y = top + h*(1-(val-low)/max(1, high-low))
                if j == 0:
                    cr.move_to(x,y)
                else:
                    cr.line_to(x,y)
            cr.stroke()

    # Playback cursor is drawn over the whole *static* history (not a growing line).
    cursor = left + w*fraction_for_time(replay, timestamp, axis)
    cr.set_source_rgba(*fg, .77)
    cr.set_line_width(1.5)
    cr.set_dash([4, 4])
    cr.move_to(cursor, top)
    cr.line_to(cursor, top+h)
    cr.stroke()
    cr.set_dash([])
    cr.set_source_rgba(*fg, .92)
    cr.arc(cursor, top, 3.2, 0, 2*math.pi)
    cr.fill()
    cr.restore()


def chart_hit_fraction(x, width):
    left, right = 58., 54.
    return min(1., max(0., (x-left)/max(1., width-left-right)))
