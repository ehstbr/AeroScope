"""Human-friendly, conservative descriptions of observed/forecast SIGMETs.

SIGMET products describe hazards to flight, not surface rain forecasts. Only
translate identifiable ICAO/NOAA codes; never manufacture hazard or validity.
No GTK or network dependency, so the presentation is regression testable.
"""
from __future__ import annotations
from .i18n import _

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re


@dataclass(frozen=True)
class SigmetExplanation:
    icon: str
    short: str
    title: str
    description: str
    fields: tuple[tuple[str, str], ...]


_HAZARDS = {
    'TS': ('⛈', _('Thunderstorms'), _('Thunderstorms with lightning that may include turbulence and heavy rain.')),
    'TURB': ('🌬', _('Turbulence'), _('Irregular air movements that may affect flight safety and comfort.')),
    'ICE': ('❄', _('Icing'), _('Potential for significant ice formation or accumulation on an aircraft.')),
    'VA': ('🌋', _('Volcanic ash'), _('Volcanic ash cloud, potentially dangerous to aircraft engines and other systems.')),
    'TC': ('🌀', _('Tropical cyclone'), _('Intense tropical system with strong winds and potentially dangerous weather conditions.')),
    'MTW': ('⛰', _('Mountain waves'), _('Terrain-generated air currents that can cause severe turbulence.')),
    'DS': ('🌫', _('Dust storm'), _('Airborne dust that may impair visibility and flight operations.')),
    'SS': ('🌫', _('Sandstorm'), _('Windblown sand that may impair visibility and flight operations.')),
    'RDOACT': ('☢', _('Radioactive cloud'), _('Radioactive cloud warning that may affect the safety of flight operations.')),
}


def _code_from(text: str) -> str | None:
    """Test complete code tokens, never substrings like TS in words."""
    t = str(text or '').upper()
    for code, pattern in (
        ('RDOACT', r'\b(?:RDOACT|RADIOACTIVE)\b'),
        ('VA', r'\b(?:VA(?:\s+ERUPTION|\s+CLD)?|VOLCANIC\s+ASH)\b'),
        ('TC', r'\b(?:TC|TROPICAL\s+CYCLONE)\b'),
        ('MTW', r'\b(?:MTW|MOUNTAIN\s+WAVE)\b'),
        ('TURB', r'\b(?:TURB(?:ULENCE)?|TB)\b'),
        ('ICE', r'\b(?:ICE|ICING|IC)\b'),
        ('TS', r'\b(?:TS(?:GR)?|THUNDERSTORMS?|CONVECTIVE)\b'),
        ('DS', r'\b(?:DS|DUST\s*STORM)\b'),
        ('SS', r'\b(?:SS|SAND\s*STORM)\b'),
    ):
        if re.search(pattern, t):
            return code
    return None


def _format_utc(value) -> str | None:
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return None
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
        except ValueError:
            return None
    return None


def _meta_field(meta, *names):
    for name in names:
        if meta.get(name) not in (None, ''):
            return meta[name]
    return None


def describe_sigmet(sigmet) -> SigmetExplanation:
    name = str(getattr(sigmet, 'name', '') or '')
    raw = str(getattr(sigmet, 'text', '') or '')
    meta = getattr(sigmet, 'metadata', None) or {}
    # Explicit NOAA phenomenon has priority over other words in the bulletin.
    code = (_code_from(str(_meta_field(meta, 'hazard', 'phenomenon', 'sigmetType') or ''))
            or _code_from(name) or _code_from(raw))
    icon, short, explanation = _HAZARDS.get(code, (
        '⚠', 'SIGMET', _('This area has an aviation weather advisory. The phenomenon could not be reliably identified from the received data.')))
    fields = []
    upper = raw.upper()
    if code == 'TS':
        parts = []
        for abbreviation, description in (
                ('OBSC', _('obscured by clouds')), ('EMBD', _('embedded in other clouds')),
                ('FRQ', _('frequent')), ('SQL', _('in a squall line')),
                ('TSGR', _('with hail'))):
            if re.search(r'\b' + abbreviation + r'\b', upper):
                parts.append(description)
        if parts:
            fields.append((_('Characteristics'), 'Tempestades ' + ', '.join(parts)))
    elif code in ('TURB', 'ICE', 'MTW') and re.search(r'\bSEV\b', upper):
        fields.append((_('Intensity'), _('Severe')))
    if code == 'ICE' and 'FZRA' in upper:
        fields.append((_('Reported cause'), _('Freezing rain')))

    if re.search(r'\bOBS\b', upper) and re.search(r'\bFCST\b', upper):
        fields.append((_('Information type'), _('Observed and forecast phenomenon')))
    elif re.search(r'\bOBS\b', upper):
        fields.append((_('Information type'), _('Observed phenomenon')))
    elif re.search(r'\bFCST\b', upper):
        fields.append((_('Information type'), _('Forecast phenomenon')))

    for label, keys in (
            (_('Issued'), ('issueTime', 'issued', 'issue_time', 'issuanceTime')),
            (_('Start of validity'), ('validTimeFrom', 'validFrom', 'startTime', 'validStart')),
            (_('End of validity'), ('validTimeTo', 'validTo', 'endTime', 'validEnd'))):
        formatted = _format_utc(_meta_field(meta, *keys))
        if formatted:
            fields.append((label, formatted))

    top = re.search(r'\bTOP\s+(?:ABV\s+)?FL\s?(\d{2,3})\b', upper)
    if top:
        fields.append((_('Reported top'), _('FL{value0} (flight level, pressure altitude)').format(value0=top.group(1))))
    movement = re.search(r'\bMOV\s+(NNE|ENE|ESE|SSE|SSW|WSW|WNW|NNW|NE|SE|SW|NW|N|E|S|W)\s+(\d{1,3})KT\b', upper)
    if movement:
        fields.append((_('Forecast movement'), _('Towards {value0}, cerca de {value1} km/h').format(value0=movement.group(1), value1=round(int(movement.group(2)) * 1.852))))
    elif re.search(r'\bSTNR\b', upper):
        fields.append((_('Movement'), _('Stationary, according to bulletin')))
    if re.search(r'\bINTSF\b', upper):
        fields.append((_('Trend'), _('Intensifying')))
    elif re.search(r'\bWKN\b', upper):
        fields.append((_('Trend'), _('Weakening')))
    elif re.search(r'\bNC\b', upper):
        fields.append((_('Trend'), _('No reported change')))

    return SigmetExplanation(icon, short, f'SIGMET · {short}', explanation, tuple(fields))


def _point_in_polygon(point, ring):
    y, x = point
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        ya, xa = a
        yb, xb = b
        if (ya > y) != (yb > y):
            cut = (xb - xa) * (y - ya) / (yb - ya) + xa
            if x < cut:
                inside = not inside
    return inside


def sigmet_label_point(rings):
    """Pick a point *inside* a SIGMET polygon, not its first edge vertex."""
    if not rings or not rings[0]:
        return None
    ring = tuple(rings[0])
    if len(ring) > 3 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return ring[0] if ring else None
    # Shoelace centroid, projected approximately as lon/lat in a regional bbox.
    sum_cross = sum(x1*y2 - x2*y1
                    for (y1,x1),(y2,x2) in zip(ring, ring[1:]+ring[:1]))
    if abs(sum_cross) > 1.e-12:
        cx = sum((x1+x2)*(x1*y2-x2*y1)
                 for (y1,x1),(y2,x2) in zip(ring, ring[1:]+ring[:1]))/(3*sum_cross)
        cy = sum((y1+y2)*(x1*y2-x2*y1)
                 for (y1,x1),(y2,x2) in zip(ring, ring[1:]+ring[:1]))/(3*sum_cross)
        if _point_in_polygon((cy, cx), ring):
            return (cy, cx)
    # Concave polygon: use the first triangle whose centroid is inside.
    for i in range(1, len(ring)-1):
        y = (ring[0][0]+ring[i][0]+ring[i+1][0])/3
        x = (ring[0][1]+ring[i][1]+ring[i+1][1])/3
        if _point_in_polygon((y, x), ring):
            return (y, x)
    return ring[0]


def sigmet_at_point(sigmets, lat: float, lon: float):
    """Find a click within a regional SIGMET boundary (geometry from NOAA)."""
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    for sigmet in reversed(tuple(sigmets)):
        for ring in sigmet.rings:
            points = tuple(ring)
            if len(points) < 3:
                continue
            # Cheap bbox rejection before a potentially costly raycast over
            # hundreds of geographic vertices on every mouse click.
            if (lat < min(p[0] for p in points) or lat > max(p[0] for p in points)
                    or lon < min(p[1] for p in points) or lon > max(p[1] for p in points)):
                continue
            if _point_in_polygon((lat, lon), points):
                return sigmet
    return None
