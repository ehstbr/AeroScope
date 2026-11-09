"""Friendly, cautious Brazilian-Portuguese rendering of NOAA METAR data.

Uses NOAA's already-decoded JSON where available. Raw METAR decoding here is
strictly a small best-effort fallback; missing fields are never invented.
Not suitable for aviation operational decisions.
"""
from __future__ import annotations
from .i18n import _

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class MetarReadable:
    condition: str
    fields: tuple[tuple[str, str], ...]


CATEGORIES = {
    'VFR': _('Visibility and cloud ceiling generally suitable for visual flight.'),
    'MVFR': _('Some visibility or cloud-ceiling restrictions.'),
    'IFR': _('Reduced visibility or cloud ceiling.'),
    'LIFR': _('Very low visibility or cloud ceiling.'),
}
CLOUDS = {
    'SKC': _('No clouds reported'), 'CLR': _('No relevant clouds reported'),
    'NSC': _('No significant clouds'), 'NCD': _('No clouds detected'),
    'FEW': _('Few clouds'), 'SCT': _('Scattered clouds'),
    'BKN': _('Mostly cloudy'), 'OVC': _('Overcast'),
    'VV': _('Obscured sky (vertical visibility)'),
}
DIRECTIONS = (_('north'), _('northeast'), _('east'), _('southeast'), _('south'), _('southwest'), _('west'), _('northwest'))
WEATHER_CODES = {
    'FZRA': _('freezing rain'), 'FZDZ': _('freezing drizzle'),
    'SHRA': _('rain showers'), 'SHSN': _('snow showers'),
    'TSRA': _('thunderstorm with rain'), 'TSSN': _('thunderstorm with snow'),
    'TS': _('thunderstorm'), 'RA': _('rain'), 'DZ': _('drizzle'), 'SN': _('snow'),
    'BR': _('mist'), 'FG': _('fog'), 'HZ': _('haze'),
    'FU': _('smoke'), 'DU': _('dust'), 'SA': _('blowing sand'),
    'GR': _('hail'), 'GS': _('small hail'), 'PL': _('ice pellets'),
    'SQ': _('strong gusts'), 'FC': _('funnel cloud'),
}


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _format_c(value):
    n = _number(value)
    return f'{n:g} °C' if n is not None and -120 <= n <= 70 else None


def _raw_fallback(report):
    """Supplement absent structured values, without claiming full METAR parsing."""
    body = ' '.join(str(report or '').upper().split(' RMK ')[0].split())[:600]
    d = {}
    wind = re.search(r'\b(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?KT\b', body)
    if wind:
        d.update(wdir=wind.group(1), wspd=int(wind.group(2)))
        if wind.group(3): d['wgst'] = int(wind.group(3))
    vsm = re.search(r'\b(P?\d+(?:/\d+)?|\d+ \d+/\d+)SM\b', body)
    if vsm: d['visib'] = vsm.group(1)
    elif ' CAVOK' in f' {body} ': d['visib_km_lower'] = 10
    elif re.search(r'\b9999\b', body): d['visib_km_lower'] = 10
    clouds = re.findall(r'\b(FEW|SCT|BKN|OVC|VV)(\d{3})\b', body)
    if clouds: d['clouds'] = [{'cover': code, 'base': int(feet)*100} for code, feet in clouds]
    elif ' CAVOK' in f' {body} ': d['clouds'] = [{'cover': 'NSC'}]
    elif re.search(r'\b(?:SKC|CLR|NSC|NCD)\b', body):
        code = re.search(r'\b(SKC|CLR|NSC|NCD)\b', body).group(1)
        d['clouds'] = [{'cover': code}]
    temps = re.search(r'\b(M?\d{2})/(M?\d{2}|//)\b', body)
    if temps:
        d['temp'] = -int(temps.group(1)[1:]) if temps.group(1).startswith('M') else int(temps.group(1))
        if temps.group(2) != '//':
            d['dewp'] = -int(temps.group(2)[1:]) if temps.group(2).startswith('M') else int(temps.group(2))
    qnh = re.search(r'\bQ(\d{4})\b', body)
    if qnh: d['altim'] = int(qnh.group(1))
    else:
        inh = re.search(r'\bA(\d{4})\b', body)
        if inh: d['altim'] = int(inh.group(1))/100*33.86388667
    codes = []
    for token in body.split():
        if token in ('CAVOK',): continue
        if re.fullmatch(r'[+-]?(?:VC)?(?:SH|TS|FZ)?(?:RA|DZ|SN|FG|BR|HZ|FU|GR|GS|PL|SQ|FC)', token):
            codes.append(token)
    if codes: d['wxString'] = ' '.join(codes[:4])
    return d


def _visibility(value, lower_km=None):
    if lower_km is not None:
        return _('At least {value0:g} km').format(value0=lower_km)
    if value is None: return None
    v = str(value).strip().upper()
    # NOAA's JSON visib uses statute miles; raw 9999 is handled separately.
    if v.startswith('P') and v[1:].replace('.', '', 1).isdigit():
        return _('More than {value0:.0f} km').format(value0=float(v[1:]) * 1.609344)
    high = v.endswith('+')
    if high: v = v[:-1]
    try:
        if '/' in v:
            whole, fraction = (v.split(' ', 1) if ' ' in v else ('0', v))
            a, b = fraction.split('/', 1)
            miles = float(whole) + float(a)/float(b)
        else:
            miles = float(v)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None
    if not 0 <= miles <= 500: return None
    km = miles*1.609344
    amount = f'{km:.1f}' if km < 10 else f'{km:.0f}'
    return f'{"Mais de " if high else ""}{amount} km'


def _wind(direction, speed, gust):
    knots = _number(speed)
    if knots is None or not 0 <= knots <= 250: return None
    if knots == 0: return _('Calm wind')
    if str(direction).strip().upper() == 'VRB':
        desc = _('Variable wind direction')
    else:
        degrees = _number(direction)
        if degrees is None or not 0 <= degrees <= 360:
            desc = _('Wind (direction not reported)')
        else:
            name = DIRECTIONS[int((degrees % 360 + 22.5)//45)%8]
            desc = _('Wind from the {value0} ({value1:.0f}°)').format(value0=name, value1=degrees)
    desc += _(', {value0} km/h ({value1} knots)').format(value0=round(knots * 1.852), value1=round(knots))
    g = _number(gust)
    if g is not None and knots < g <= 300:
        desc += _('; gusting up to {value0} km/h').format(value0=round(g * 1.852))
    return desc


def _clouds(value):
    if not isinstance(value, (list, tuple)): return None
    descriptions = []
    for item in value[:3]:
        if not isinstance(item, dict): continue
        code = str(item.get('cover') or '').upper()
        if code not in CLOUDS: continue
        text = CLOUDS[code]
        base = _number(item.get('base'))
        if base is not None and 0 <= base <= 60000:
            text += _(' at approximately {value0:,} m above the airport').format(value0=round(base * 0.3048)).replace(',', '.')
        descriptions.append(text)
    return '; '.join(descriptions) if descriptions else None


def _weather(value):
    if not isinstance(value, str) or not value.strip(): return None
    results=[]
    for original in value.upper().replace(',', ' ').split()[:5]:
        code = original
        intensity = _('light') if code.startswith('-') else (_('heavy') if code.startswith('+') else '')
        code = code.lstrip('+-')
        vicinity = code.startswith('VC')
        if vicinity: code = code[2:]
        phrase = WEATHER_CODES.get(code)
        if phrase is None: continue
        if intensity:
            phrase += f' ({intensity})'
        if vicinity: phrase += _(' nearby')
        results.append(phrase)
    return ', '.join(results) if results else None


def describe_metar(metar) -> MetarReadable:
    """Describe a NOAA Metar in common language; never fabricate missing data."""
    fields = dict(_raw_fallback(getattr(metar, 'raw', '')))
    fields.update({key: value for key, value in (getattr(metar, 'details', None) or {}).items()
                   if value is not None and value != ''})
    if fields.get('visib') is not None:
        fields.pop('visib_km_lower', None)  # Prefer NOAA decoded visibility over raw 9999/CAVOK.
    category = str(getattr(metar, 'category', '') or '').upper()
    condition = CATEGORIES.get(category, _('Flight conditions not classified in this report.'))
    pairs=[]
    wx = _weather(fields.get('wxString'))
    if wx: pairs.append((_('Observed weather'), wx.capitalize()))
    temperature = _format_c(fields.get('temp'))
    if temperature: pairs.append((_('Temperature'), temperature))
    dewpoint = _format_c(fields.get('dewp'))
    if dewpoint: pairs.append((_('Dew point'), dewpoint))
    wind = _wind(fields.get('wdir'), fields.get('wspd'), fields.get('wgst'))
    if wind: pairs.append((_('Wind'), wind))
    visibility = _visibility(fields.get('visib'), fields.get('visib_km_lower'))
    if visibility: pairs.append((_('Visibility'), visibility))
    clouds = _clouds(fields.get('clouds'))
    if clouds: pairs.append((_('Clouds'), clouds))
    pressure = _number(fields.get('altim'))
    if pressure is not None and 870 <= pressure <= 1100:
        pairs.append((_('Atmospheric pressure (QNH)'), f'{pressure:g} hPa'))
    return MetarReadable(condition, tuple(pairs))
