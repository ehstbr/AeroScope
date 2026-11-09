"""Desktop-independent, privacy-conscious location fallback policy.

GeoClue is a freedesktop.org service and does not require GNOME Shell.
GNOME's own location kill switch is inspected only on GNOME desktops.
No IP geolocation request is performed by these helpers.
"""
from __future__ import annotations
from .i18n import _
import os


def is_gnome_desktop(environ=None):
    env = os.environ if environ is None else environ
    desktop = ':'.join([str(env.get('XDG_CURRENT_DESKTOP') or ''),
                        str(env.get('XDG_SESSION_DESKTOP') or '')]).upper()
    return 'GNOME' in desktop.split(':') or any(
        part == 'GNOME' for part in desktop.replace(';', ':').split(':'))


def system_location_status(gio, geoclue_available, environ=None):
    """Return (try|disabled|unavailable, explanation).

    Does not assume GNOME GSettings exists outside GNOME, nor activate
    GeoClue or contact external websites during the check.
    """
    if is_gnome_desktop(environ):
        try:
            source = gio.SettingsSchemaSource.get_default()
            schema = source.lookup('org.gnome.system.location', True) if source else None
            if schema is not None and schema.has_key('enabled'):
                if not gio.Settings.new('org.gnome.system.location').get_boolean('enabled'):
                    return 'disabled', _('Location is disabled in GNOME settings.')
        except Exception:
            # Fallback to the freedesktop service; do not assume the setting.
            pass
    if not geoclue_available:
        return 'unavailable', _('GeoClue is not installed or available on this system.')
    return 'try', ''


def should_suggest_ip(settings, already_offered, demo=False, user_initiated=False):
    """Respect the opt-out while allowing a fresh manual attempt after "Agora não".

    Only unsolicited offers are limited to once per session. Clicking the
    geolocation control is an explicit new request, not an unsolicited offer;
    neither path ever contacts the IP service before consent.
    """
    return (not demo and (user_initiated or not already_offered)
            and bool(settings.get('suggest_ip_fallback', True)))
