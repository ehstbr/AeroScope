"""Per-user XDG Autostart for monitoring after the desktop login.

Never installs system-wide services or requires root. In a session without a
StatusNotifier tray, the app falls back to showing the normal window so it
cannot silently become inaccessible.
"""
from __future__ import annotations
import os
from pathlib import Path

ENTRY_NAME = 'io.github.ehstbr.Aeroscope.desktop'
ENTRY = '[Desktop Entry]\nType=Application\nName=AeroScope — Flight Monitor\nName[pt_BR]=AeroScope — Monitor de Voos\nComment=Monitor favorites and emergencies after login\nComment[pt_BR]=Monitora favoritos e emergências após o login\nExec=aeroscope --background\nTryExec=aeroscope\nIcon=io.github.ehstbr.Aeroscope\nTerminal=false\nX-GNOME-Autostart-enabled=true\nStartupNotify=false\nCategories=Science;Utility;\n'


def entry_path() -> Path:
    config = os.environ.get('XDG_CONFIG_HOME')
    root = Path(config) if config else Path.home() / '.config'
    return root / 'autostart' / ENTRY_NAME


def enabled() -> bool:
    try:
        lines = entry_path().read_text('utf-8').splitlines()
        fields = {}
        for line in lines:
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                fields[key.strip()] = value.strip()
        return (fields.get('Hidden', 'false').lower() != 'true'
                and fields.get('Exec') == 'aeroscope --background'
                and fields.get('Type') == 'Application')
    except (OSError, UnicodeError):
        return False


def configure(want_enabled: bool) -> None:
    """Only ever create or remove the AeroScope-owned user entry."""
    target = entry_path()
    if want_enabled:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.desktop.tmp')
        temp.write_text(ENTRY, 'utf-8')
        temp.replace(target)
    elif target.is_file():
        # Do not delete an unrelated custom autostart entry with same name.
        if enabled():
            target.unlink()
