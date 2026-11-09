"""Low-contrast visual styles shared by SIGMET symbols and polygon boundaries.

The NOAA phenomenon is classified with the *same* parser as the Portuguese
weather description, including metadata-first priority. No GUI dependencies.
"""
from __future__ import annotations
from .i18n import _
from dataclasses import dataclass
from .sigmet_readable import describe_sigmet

@dataclass(frozen=True)
class SigmetStyle:
    key: str
    rgb: tuple[float, float, float]

# Sufficient distinction on both light and dark map sources, with intentionally
# restrained polygon opacity. Storms orange, ice blue, turbulence golden, etc.
COLORS = {
    'storm': SigmetStyle('storm', (0.94, 0.45, 0.17)),
    'turbulence': SigmetStyle('turbulence', (0.83, 0.65, 0.22)),
    'icing': SigmetStyle('icing', (0.28, 0.60, 0.90)),
    'volcanic': SigmetStyle('volcanic', (0.62, 0.44, 0.35)),
    'cyclone': SigmetStyle('cyclone', (0.67, 0.45, 0.82)),
    'mountain': SigmetStyle('mountain', (0.26, 0.67, 0.64)),
    'dust': SigmetStyle('dust', (0.72, 0.53, 0.34)),
    'radioactive': SigmetStyle('radioactive', (0.81, 0.36, 0.40)),
    'generic': SigmetStyle('generic', (0.56, 0.64, 0.73)),
}
LEGACY = SigmetStyle('legacy', (1.0, 0.57, 0.13))

_BY_DESCRIPTION = {
    _('Thunderstorms'): 'storm',
    _('Turbulence'): 'turbulence',
    _('Icing'): 'icing',
    _('Volcanic ash'): 'volcanic',
    _('Tropical cyclone'): 'cyclone',
    _('Mountain waves'): 'mountain',
    _('Dust storm'): 'dust',
    _('Sandstorm'): 'dust',
    _('Radioactive cloud'): 'radioactive',
}


def classify_sigmet(advisory) -> SigmetStyle:
    return COLORS[_BY_DESCRIPTION.get(describe_sigmet(advisory).short, 'generic')]


def display_style(style: SigmetStyle, colors_enabled: bool) -> SigmetStyle:
    return style if colors_enabled else LEGACY


def sigmet_alpha(selected: bool, tower: bool, *, filled: bool = True) -> tuple[float, float]:
    """Return (fill alpha, contour alpha) independent of the map's background.

    The tower darkens the fill only; selected contour remains legible.
    """
    fill = (0.18 if selected else 0.10) if filled else 0.0
    if tower:
        fill *= 0.65
    return (fill, 0.96 if selected else 0.72)
