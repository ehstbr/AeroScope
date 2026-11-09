"""Pure policy for regional ADS-B polling across main/PiP/tray modes."""
from __future__ import annotations
from .i18n import _, ngettext

INTERVALS = (10, 15, 20, 30, 45, 60, 120, 240, 480, 600)
BACKGROUND_INTERVALS = (0,) + INTERVALS


def describe_interval(seconds: int) -> str:
    if seconds == 0:
        return _('Disabled — favorites and emergencies only')
    if seconds >= 60 and seconds % 60 == 0:
        n = seconds // 60
        return ngettext('{n} minute', '{n} minutes', n).format(n=n)
    return ngettext('{n} second', '{n} seconds', seconds).format(n=seconds)


def regional_mode(*, started: bool, main_visible: bool, pip_visible: bool,
                  visible_seconds: int, background_seconds: int) -> tuple[str, int]:
    """Mode+cadence. New silent autostarts never query the region until shown.

    A map remains 'open' when the main window is minimized but not hidden.
    'background' means there is no visible main/PiP window and this session
    has previously opened a map. Zero means periodic regional polling off.
    """
    if main_visible or pip_visible:
        return 'foreground', visible_seconds
    if not started:
        return 'dormant', 0
    if background_seconds == 0:
        return 'paused', 0
    return 'background', background_seconds
