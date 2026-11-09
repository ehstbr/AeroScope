"""Small, honest visual descriptions of airport METAR availability.

Do not infer a flight category or current weather from the airport location.
A category comes only from an actual, successfully decoded NOAA observation.
"""
from __future__ import annotations
from .i18n import _

VALID_CATEGORIES = frozenset({'VFR', 'MVFR', 'IFR', 'LIFR'})


def metar_category(report):
    category = str(getattr(report, 'category', '') or '').strip().upper()
    return category if category in VALID_CATEGORIES else None


def metar_badge(report):
    """A genuine observation may lack a NOAA VFR/IFR category.

    Display METAR (not an invented VFR status) in that case. This is
    especially important for smaller airports such as SBBH/PLU.
    """
    category = metar_category(report)
    if category:
        return category
    if report is not None and str(getattr(report, 'raw', '') or '').strip():
        return 'METAR'
    return None


def airport_marker_text(iata: str, report=None, *, metar_enabled=False) -> str:
    label = str(iata).strip().upper()
    badge = metar_badge(report) if metar_enabled else None
    return f'{label} · {badge}' if badge else label


def station_marker_text(station: str, report=None) -> str:
    badge = metar_badge(report)
    return f'{station} · {badge}' if badge else str(station)


def airport_metar_tooltip(name: str, iata: str, icao: str, report=None, *, enabled=False) -> str:
    info = f'{name}\n{iata} / {icao}'
    if not enabled:
        return info + _('\nClick for details and weather')
    category = metar_category(report)
    if category:
        info += f'\nMETAR NOAA: {category}'
        observed = str(getattr(report, 'observed', '') or '').strip()
        if observed:
            info += f' · {observed[:40]}'
    else:
        info += _('\nMETAR: no observation available yet')
    return info + _('\nClick for details and weather')
