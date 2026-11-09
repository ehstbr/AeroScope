"""English-initial, Alt-modified AeroScope keyboard shortcuts.

Require Alt for application commands, preserve Ctrl-based text editing, and
leave function-key accelerators unmodified.
"""
from .i18n import _


def keyboard_command(key_name, *, ctrl=False, alt=False, super_key=False,
                     editing=False):
    """Resolve a GDK key name to a command only for Alt (never Ctrl)."""
    # Pass through all Ctrl bindings (including Ctrl+A/C/V) so GTK retains
    # native Select All, Copy, Paste and other text-editor shortcuts.
    if not key_name or not alt or ctrl or super_key:
        return None
    key = key_name.lower()
    if key in ('plus', 'equal', 'kp_add'):
        # On several layouts + shares the = key; keypad + is supported too.
        return 'zoom-in'
    if key in ('minus', 'kp_subtract'):
        return 'zoom-out'
    if key in ('period', 'kp_decimal', 'kp_separator', 'l'):
        return 'locate'
    if key in ('question',):
        return 'shortcuts'
    return {
        'a': 'advisories',         # SIGMET advisories
        'v': 'visible',            # Visible aircraft
        'f': 'search',            # Find
        't': 'tower',             # Tower
        's': 'sweep',             # Sweep
        'm': 'metar',             # METAR
        'p': 'pip',               # Picture in Picture
        'b': 'bookmarks',         # Bookmarks
        'e': 'emergencies',       # Emergencies
    }.get(key)


# Menu-only presentation metadata for shortcuts that already work.  The
# window's key controller keeps handling Alt commands (including those with
# stateful actions); F1/F11 and app commands retain native Gtk accelerators.
# Do not assign shortcuts to menu entries that have no matching command.
MENU_ACCELERATORS = {
    'app.monitor': '<Alt>b',
    'app.global-alerts': '<Alt>e',
    'app.toggle-tower': '<Alt>t',
    'app.toggle-sweep': '<Alt>s',
    'app.toggle-weather-metar': '<Alt>m',
    'app.toggle-weather-sigmet': '<Alt>a',
    'app.toggle-dashboard': 'F11',
    'app.pip': '<Alt>p',
    'app.preferences': '<Alt>comma',
    'app.shortcuts': 'F1',
    'app.quit': '<Alt>q',
}


def shortcut_groups():
    """Labels for one single-header shortcuts reference window."""
    return (
        (_('Map and navigation'), (
            (_('Zoom in'), '<Alt>plus', _('Alt++ or Alt+keypad +')),
            (_('Zoom out'), '<Alt>minus', _('Alt+− or Alt+keypad −')),
            (_('Locate on map'), '<Alt>period', _('Alt+. or Alt+L')),
            (_('Find aircraft, airports or cities'), '<Alt>f', _('Alt+F')),
            (_('Full screen dashboard'), 'F11', _('F11')),
        )),
        (_('Layers and monitoring'), (
            (_('Control tower mode'), '<Alt>t', _('Alt+T')),
            (_('Rotating sweep'), '<Alt>s', _('Alt+S')),
            (_('METAR observations'), '<Alt>m', _('Alt+M')),
            (_('SIGMET advisories'), '<Alt>a', _('Alt+A')),
            (_('Mini-map'), '<Alt>p', _('Alt+P')),
            (_('Favorites'), '<Alt>b', _('Alt+B')),
            (_('Visible aircraft'), '<Alt>v', _('Alt+V')),
            (_('Emergencies'), '<Alt>e', _('Alt+E')),
        )),
        (_('Application'), (
            (_('Keyboard shortcuts'), 'F1', _('F1')),
            (_('Preferences'), '<Alt>comma', _('Alt+,')),
            (_('Quit AeroScope'), '<Alt>q', _('Alt+Q')),
            (_('Exit full screen'), 'Escape', _('Esc')),
        )),
    )
