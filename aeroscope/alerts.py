"""Human-readable ADS-B transponder priority status, without inferring MAYDAY.

Sources: squawk codes and the optional ADS-B `emergency` priority field.
No transponder status proves that a pilot made a voice MAYDAY/PAN-PAN call.
"""
from __future__ import annotations
from .i18n import _
from dataclasses import dataclass

@dataclass(frozen=True)
class AircraftAlert:
    level: str  # none, info, warning, critical
    label: str
    detail: str

NONE = AircraftAlert('none', '', '')

def classify_alert(squawk: str = '', emergency: str = '') -> AircraftAlert:
    sq = str(squawk or '').strip()
    status = str(emergency or '').strip().lower()
    if sq == '7500' or status == 'unlawful':
        return AircraftAlert('critical', _('Unlawful interference'),
                             _('Code 7500 or ADS-B signal of unlawful interference; situation not independently confirmed.'))
    if sq == '7700' or status in ('general', 'downed'):
        return AircraftAlert('critical', _('Emergency signaled'),
                             _('Code 7700 or ADS-B emergency signal; does not confirm a MAYDAY declaration.'))
    if sq == '7600' or status == 'nordo':
        return AircraftAlert('warning', _('Communication failure'),
                             _('Code 7600 or ADS-B signal of radio failure; severity cannot be inferred.'))
    if status == 'minfuel':
        return AircraftAlert('warning', _('Minimum fuel'),
                             _('Aircraft indicates fuel priority; this does not necessarily mean a declared emergency.'))
    if status == 'lifeguard':
        return AircraftAlert('info', _('Priority operation'),
                             _('Priority/medical support signal; not necessarily an emergency.'))
    return NONE
