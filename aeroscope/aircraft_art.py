"""Illustrations and readable model names for aircraft reported by ADS-B.

The ICAO type designator is only a model hint, not guaranteed accurate.
Rendering is Cairo-only and deliberately independent of GTK/GI for testing.
The silhouettes indicate a *category*, not a scale drawing of the airframe.
"""
from __future__ import annotations
from .i18n import _
import math

MODEL_NAMES = {
    'B772': 'Boeing 777-200', 'B77L': 'Boeing 777-200LR',
    'B773': 'Boeing 777-300', 'B77W': 'Boeing 777-300ER', 'B77F': 'Boeing 777F',
    'B788': 'Boeing 787-8', 'B789': 'Boeing 787-9', 'B78X': 'Boeing 787-10',
    'B744': 'Boeing 747-400', 'B748': 'Boeing 747-8',
    'B738': 'Boeing 737-800', 'B737': 'Boeing 737-700', 'B739': 'Boeing 737-900',
    'B38M': 'Boeing 737 MAX 8', 'B39M': 'Boeing 737 MAX 9',
    'A319': 'Airbus A319', 'A320': 'Airbus A320', 'A321': 'Airbus A321',
    'A20N': 'Airbus A320neo', 'A21N': 'Airbus A321neo',
    'A333': 'Airbus A330-300', 'A332': 'Airbus A330-200',
    'A359': 'Airbus A350-900', 'A35K': 'Airbus A350-1000',
    'A388': 'Airbus A380-800',
    'E170': 'Embraer 170', 'E175': 'Embraer 175',
    'E190': 'Embraer 190', 'E195': 'Embraer 195',
    'E290': 'Embraer E190-E2', 'E295': 'Embraer E195-E2',
    'AT72': 'ATR 72', 'AT75': 'ATR 72', 'AT76': 'ATR 72-600',
    'AT43': 'ATR 42', 'DH8D': 'De Havilland Dash 8-400',
    'C172': 'Cessna 172', 'C182': 'Cessna 182', 'PA28': 'Piper PA-28',
    'DA40': 'Diamond DA40', 'SR22': 'Cirrus SR22',
    'BE20': 'Beechcraft King Air 200', 'B350': 'Beechcraft King Air 350',
    'R44': 'Robinson R44', 'R22': 'Robinson R22',
    'H125': 'Airbus H125', 'EC35': 'Airbus H135', 'EC45': 'Airbus H145',
}

WIDEBODY = {'B772', 'B77L', 'B773', 'B77W', 'B77F', 'B788', 'B789', 'B78X',
            'B744', 'B748', 'A332', 'A333', 'A359', 'A35K', 'A388'}
REGIONAL = {'E170', 'E175', 'E190', 'E195', 'E290', 'E295', 'CRJ2', 'CRJ7', 'CRJ9'}
TURBOPROP = {'AT43', 'AT72', 'AT75', 'AT76', 'DH8D', 'B350', 'BE20', 'SF34'}
LIGHT = {'C172', 'C182', 'PA28', 'DA40', 'SR22', 'C152', 'C206', 'C208'}
HELICOPTER = {'R44', 'R22', 'H125', 'EC35', 'EC45', 'B06', 'B407', 'S76'}


def aircraft_kind(icao_type: str) -> str:
    code = (icao_type or '').strip().upper()
    if code in HELICOPTER:
        return 'helicopter'
    if code in LIGHT:
        return 'light'
    if code in TURBOPROP:
        return 'turboprop'
    if code in REGIONAL or code.startswith('E19') or code.startswith('E29'):
        return 'regional'
    if code in WIDEBODY or code.startswith(('B77', 'B78', 'A33', 'A35')):
        return 'widebody'
    return 'jet'


def aircraft_name(icao_type: str) -> str:
    code = (icao_type or '').strip().upper()
    return MODEL_NAMES.get(code, _('ICAO type {value0}').format(value0=code) if code else _('Unknown model'))


def aircraft_category(icao_type: str) -> str:
    return {
        'helicopter': _('Helicopter'),
        'light': _('Light aviation'),
        'turboprop': _('Turboprop'),
        'regional': _('Regional jet'),
        'widebody': _('Wide-body jet'),
        'jet': _('Jet aircraft / unidentified'),
    }[aircraft_kind(icao_type)]


def _path(cr, points):
    cr.move_to(*points[0])
    for x, y in points[1:]:
        cr.line_to(x, y)
    cr.close_path()


def _fill_outline(cr, points, color=(.97, .98, 1.0)):
    _path(cr, points)
    cr.set_source_rgba(.12, .22, .30, .95)
    cr.set_line_width(1.5)
    cr.stroke_preserve()
    cr.set_source_rgb(*color)
    cr.fill()


def _engine(cr, x, y, size=1.0):
    cr.save()
    cr.translate(x, y)
    cr.scale(size, size)
    cr.set_source_rgb(.18, .30, .39)
    cr.arc(0, 0, 2.2, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(.83, .90, .96)
    cr.arc(0, -.5, 1.6, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def _jet(cr, wide=False, regional=False):
    wings = 18 if regional else (23.5 if wide else 20)
    length = 18 if regional else (24 if wide else 21)
    fus = 2.4 if regional else (3.7 if wide else 3)
    # Main wings have a recognisable swept-back leading edge.
    _fill_outline(cr, [(-fus, -7), (-wings, 6), (-wings, 9), (-fus, 2.8),
                       (fus, 2.8), (wings, 9), (wings, 6), (fus, -7)],
                  (.91, .95, .98))
    # Tailplanes, deliberately separate from the main wings.
    _fill_outline(cr, [(-2, 10), (-9, 16), (-9, 18), (0, 15),
                       (9, 18), (9, 16), (2, 10)], (.84, .90, .95))
    if wide:
        _engine(cr, -10.3, 8, 1.35)
        _engine(cr, 10.3, 8, 1.35)
    else:
        _engine(cr, -8.0, 6.3, .95 if regional else 1.1)
        _engine(cr, 8.0, 6.3, .95 if regional else 1.1)
    # Narrowing fuselage and cockpit; silhouette points north (track=0).
    cr.move_to(0, -length)
    cr.curve_to(-fus - .7, -length + 3, -fus, -9, -fus, 7)
    cr.line_to(-2, 14)
    cr.line_to(0, 17)
    cr.line_to(2, 14)
    cr.line_to(fus, 7)
    cr.curve_to(fus, -9, fus + .7, -length + 3, 0, -length)
    cr.close_path()
    cr.set_source_rgb(.12, .22, .30)
    cr.set_line_width(1.6)
    cr.stroke_preserve()
    cr.set_source_rgb(.99, .99, 1)
    cr.fill()
    cr.set_source_rgb(.28, .48, .61)
    _path(cr, [(-2.3, -length + 5), (-1.25, -length + 3),
               (1.25, -length + 3), (2.3, -length + 5), (1.6, -length + 7),
               (-1.6, -length + 7)])
    cr.fill()
    cr.set_source_rgb(.64, .72, .77)
    cr.set_line_width(.65)
    cr.move_to(0, -length + 9)
    cr.line_to(0, 13)
    cr.stroke()


def _prop(cr, light=False):
    wings = 19 if light else 23
    # Mostly straight wings distinguish props from swept-wing jets.
    _fill_outline(cr, [(-wings, -1), (-wings, 3.3), (wings, 3.3),
                       (wings, -1), (1.4, -3), (-1.4, -3)], (.91, .96, .98))
    if not light:
        _engine(cr, -10, 1, 1.25)
        _engine(cr, 10, 1, 1.25)
    _fill_outline(cr, [(-2.2, -17), (-3, -12), (-2.4, 11), (-10, 14),
                       (-10, 16), (0, 14), (10, 16), (10, 14),
                       (2.4, 11), (3, -12), (2.2, -17)], (.98, .99, 1))
    cr.set_source_rgb(.31, .53, .66)
    _path(cr, [(-2.5, -11), (0, -14), (2.5, -11), (2, -7), (-2, -7)])
    cr.fill()
    if light:
        cr.set_source_rgba(.18, .32, .43, .9)
        cr.set_line_width(1.9)
        cr.move_to(-7, -17)
        cr.line_to(7, -17)
        cr.stroke()


def _helicopter(cr):
    # Rotor / skid geometry instead of a jet silhouette.
    cr.set_source_rgb(.18, .30, .40)
    cr.set_line_width(2.4)
    cr.move_to(-22, -4)
    cr.line_to(22, -4)
    cr.move_to(0, -16)
    cr.line_to(0, 21)
    cr.stroke()
    cr.set_source_rgb(.76, .86, .92)
    cr.set_line_width(1.8)
    cr.move_to(-9, 13)
    cr.line_to(-9, -2)
    cr.move_to(9, 13)
    cr.line_to(9, -2)
    cr.move_to(-12, 13)
    cr.line_to(-6, 13)
    cr.move_to(6, 13)
    cr.line_to(12, 13)
    cr.stroke()
    cr.set_source_rgb(.17, .34, .46)
    cr.arc(0, -5, 9, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(.97, .99, 1)
    cr.arc(0, -5, 7.6, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(.37, .64, .75)
    cr.arc(0, -7, 4.3, 0, 2 * math.pi)
    cr.fill()


def _draw_kind(cr, kind):
    if kind == 'helicopter':
        _helicopter(cr)
    elif kind in ('turboprop', 'light'):
        _prop(cr, light=(kind == 'light'))
    else:
        _jet(cr, wide=(kind == 'widebody'), regional=(kind == 'regional'))


def _alert_badge(cr, level):
    """Tiny corner badge for actual reported transponder conditions only."""
    if level not in ('critical', 'warning', 'info'):
        return
    cr.save()
    if level == 'critical':
        color = (.85, .11, .15)
    elif level == 'warning':
        color = (.90, .52, .04)
    else:
        color = (.13, .49, .77)
    cr.set_source_rgb(*color)
    cr.arc(47.0, 9.0, 7.2, 0, 2 * math.pi)
    cr.fill_preserve()
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(1.4)
    cr.stroke()
    cr.select_font_face('Sans', 0, 1)
    cr.set_font_size(10.8)
    extents = cr.text_extents('!')
    cr.move_to(47.0 - (extents.width/2 + extents.x_bearing),
               9.0 - (extents.height/2 + extents.y_bearing))
    cr.show_text('!')
    cr.restore()


def altitude_visual_scale(altitude_ft: float | None) -> float:
    """Very subtle cartographic perspective, not a physical wingspan scale.

    Top-down airplane symbols are conventional markers; a realistic camera
    projection cannot be computed from flight altitude alone. Keep aircraft
    readable and avoid implying an aircraft's actual physical dimensions.
    """
    if altitude_ft is None:
        return 0.90  # 'ground' from ADS-B
    try:
        altitude = float(altitude_ft)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(altitude):
        return 1.0
    fraction = min(1.0, max(0.0, altitude) / 39000.0)
    return 0.90 + 0.18 * fraction ** 0.70


def paint_aircraft(cr, icao_type: str, track: float, selected=False,
                   highlighted=False, alert_level='none', altitude_ft=None):
    """56px symbol: distinct selection, discreet hover and scaled silhouette.

    The size factor applies to the drawing only, never the 56px hit area or
    status badge. The shaded region matches the aircraft shape, not a disc.
    """
    kind = aircraft_kind(icao_type)
    factor = altitude_visual_scale(altitude_ft)
    cr.save()
    cr.translate(28, 28)

    if selected:
        # Explicit selection retains the stronger circular GNOME accent ring.
        cr.set_source_rgba(.10, .46, .78, .10)
        cr.arc(0, 0, 26, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(.10, .46, .78, .85)
        cr.set_line_width(1.8)
        cr.arc(0, 0, 25, 0, 2 * math.pi)
        cr.stroke()
    elif highlighted:
        # Hover should read as a gentle outline of the *airframe*, not a
        # second selection ring. Enlarge a translucent silhouette slightly.
        cr.save()
        cr.rotate(math.radians(track % 360))
        cr.scale(factor * 1.12, factor * 1.12)
        cr.push_group()
        _draw_kind(cr, kind)
        silhouette = cr.pop_group()
        cr.set_source_rgba(.08, .48, .75, .34)
        cr.mask(silhouette)
        cr.restore()

    cr.save()
    cr.translate(1.6, 2.2)
    cr.rotate(math.radians(track % 360))
    cr.scale(factor, factor)
    cr.push_group()
    _draw_kind(cr, kind)
    shadow = cr.pop_group()
    cr.set_source_rgba(.025, .065, .10, .24)
    cr.mask(shadow)
    cr.restore()

    cr.rotate(math.radians(track % 360))
    cr.scale(factor, factor)
    _draw_kind(cr, kind)
    cr.restore()
    _alert_badge(cr, alert_level)


def paint_replay_aircraft(cr, icao_type: str, bearing: float):
    """Archival marker: real category silhouette, violet instead of white.

    No rectangular badge, no glyph, and the nose uses the timestamped bearing.
    This intentionally has the same 56px canvas as a live aircraft marker.
    """
    cr.save()
    cr.translate(28, 28)
    cr.rotate(math.radians(bearing % 360))
    kind = aircraft_kind(icao_type)
    cr.save()
    cr.translate(1.5, 2)
    cr.push_group()
    _draw_kind(cr, kind)
    shape = cr.pop_group()
    cr.set_source_rgba(.03, .03, .11, .35)
    cr.mask(shape)
    cr.restore()
    cr.push_group()
    _draw_kind(cr, kind)
    shape = cr.pop_group()
    cr.set_source(shape)
    cr.paint()
    # Preserve the rendered engine, cockpit and fuselage detail underneath.
    cr.set_source_rgba(.43, .26, .78, .67)
    cr.mask(shape)
    cr.restore()


def paint_favorite_star(cr, x=44.0, y=12.5, radius=7.0):
    """Draw a small amber favorite badge, independent of selection/hover.

    The star is rendered in map coordinates, so it does not rotate with the
    aircraft or look like an emergency ring. No external icon/theme required.
    """
    import math
    cr.save()
    cr.new_path()
    for i in range(10):
        r = radius if i % 2 == 0 else radius * .45
        a = -math.pi / 2 + i * math.pi / 5
        px, py = x + r * math.cos(a), y + r * math.sin(a)
        if i == 0:
            cr.move_to(px, py)
        else:
            cr.line_to(px, py)
    cr.close_path()
    cr.set_source_rgb(1.0, .79, .14)
    cr.fill_preserve()
    cr.set_source_rgb(.31, .21, .05)
    cr.set_line_width(1.6)
    cr.stroke()
    cr.restore()
