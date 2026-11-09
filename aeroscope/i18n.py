"""GNU Gettext integration for AeroScope.

English (United States) is the native source language. In automatic mode,
the desktop locale determines the translation. An explicit setting is loaded before
module-level aviation vocabulary is initialized. Language changes take effect
on the next process start, as required by the GTK interface lifecycle.
"""
from __future__ import annotations

import gettext
import json
import os
import locale
from pathlib import Path

DOMAIN = 'aeroscope'
SUPPORTED_LANGUAGES = ('en_US', 'pt_BR')


def _system_language() -> str:
    """Honor the session language (including LANGUAGE from Ubuntu/GNOME).

    Non-Brazilian or unsupported locales fall back to the native en_US texts.
    This deliberately does not change the process-wide numeric/GTK locale.
    """
    def matching(code: str) -> str | None:
        code = code.strip().split('.', 1)[0].split('@', 1)[0].replace('-', '_').lower()
        if code in ('pt_br', 'pt'):
            return 'pt_BR'
        if code == 'en_us' or code in ('c', 'posix') or code.startswith('en_'):
            return 'en_US'
        return None

    # LANGUAGE is a colon-separated language preference supplied by GNOME.
    # It takes precedence over LANG in gettext-enabled non-C desktop sessions.
    for code in os.environ.get('LANGUAGE', '').split(':'):
        found = matching(code)
        if found:
            return found
    for key in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        found = matching(os.environ.get(key, ''))
        if found:
            return found
    try:
        current, _encoding = locale.getlocale(locale.LC_MESSAGES)
        found = matching(current or '')
        if found:
            return found
    except (ValueError, TypeError):
        pass
    return 'en_US'


def _configured_language() -> str:
    override = os.environ.get('AEROSCOPE_LANGUAGE')
    if override in SUPPORTED_LANGUAGES:
        return override
    if override == 'auto':
        return _system_language()
    try:
        config = (Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
                  / 'aeroscope' / 'settings.json')
        data = json.loads(config.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            selected = data.get('language', 'auto')
            if selected == 'pt_BR':
                return selected
            # Pre-0.3.51 saves often contain 'en_US' even if the user never
            # picked English. Migrate these to Automatic on first upgrade.
            if selected == 'en_US' and data.get('language_schema') == 2:
                return selected
    except (OSError, ValueError, TypeError):
        pass
    return _system_language()

LANGUAGE = _configured_language()


def _catalog() -> gettext.NullTranslations:
    if LANGUAGE == 'en_US':
        return gettext.NullTranslations()
    # Source checkout works with the compiled catalogs shipped in the ZIP;
    # standard Debian installations also expose /usr/share/locale.
    local = Path(__file__).resolve().parent / 'locale'
    for directory in (local, Path('/usr/share/locale')):
        try:
            return gettext.translation(DOMAIN, localedir=str(directory), languages=[LANGUAGE])
        except (FileNotFoundError, OSError):
            continue
    return gettext.NullTranslations()


_TRANSLATION = _catalog()


def _(message: str) -> str:
    """Translate a fixed English-language Gettext message identifier."""
    return _TRANSLATION.gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    return _TRANSLATION.ngettext(singular, plural, count)
