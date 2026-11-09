"""Small pure state policy for AeroScope's optional background operation."""
from __future__ import annotations


def close_behavior(*, background_enabled: bool, pip_enabled: bool,
                   indicator_available: bool, warning_accepted: bool = False) -> str:
    """Return 'quit', 'pip', 'hide' or 'confirm' without trapping the user.

    GNOME environments may not expose the StatusNotifier watcher at all.
    When hiding without a tray, ask once before making the main window
    invisible. It can still be restored from the desktop launcher.
    """
    if pip_enabled:
        return 'pip'
    if not background_enabled:
        return 'quit'
    if indicator_available or warning_accepted:
        return 'hide'
    return 'confirm'


def can_monitor_in_background(*, background_active: bool, window_mapped: bool,
                              demo: bool) -> bool:
    return not demo and (background_active or window_mapped)
