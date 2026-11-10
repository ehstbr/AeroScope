"""Small, transparent XDG settings/cache store for AeroScope.

The last map viewport can be persisted by user request; GPS/IP locations
and ADS-B trails are not saved by this settings module.
"""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from .regional_poll import INTERVALS, BACKGROUND_INTERVALS
from .autostart import enabled as autostart_enabled

APP_ID = 'io.github.ehstbr.Aeroscope'
GITHUB = 'https://github.com/ehstbr/Aeroscope'
VERSION = '0.3.72'
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'aeroscope'
CACHE_DIR = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'aeroscope'
DEFAULT = {
    'language': 'auto',       # Follow Ubuntu/GNOME; native fallback remains en_US.
    'language_schema': 2,     # Disambiguates implicit en_US from 0.3.50.
    'theme': 'system',           # system, light, dark
    'map': 'osm',               # osm, topo, hiking
    'tower': False,
    'background_on_close': True,  # keep monitoring after close if tray or accepted fallback
    'pip_always_on_top': True,    # X11 window-manager hint; Wayland not portable
    'close_to_pip': False,        # optionally show small live map on close
    'marker_label': 'off',  # off, registration (fallback ICAO24), icao
    'clock_ring': True,  # independent hour clock around the selected aircraft
    'tower_sweep': False,  # visual scanning beam; reveal positions after pass
    'refresh': 10,           # mapa principal ou PiP visível
    'refresh_background': 10, # mapa fechado, somente bandeja; 0 para desativar
    'autostart_login': False, # managed by per-user XDG autostart file
    'speed': 'kmh',             # kmh, kt, mph
    'enable_hover': True,
    'startup_splash': True,     # GNOME overlay while loading the first three snapshots
    'animate_aircraft': True,    # animate until the next scheduled poll
    'altitude_perspective': True, # very gentle airframe size variation by altitude
    'history': True,
    'photos': True,
    'show_airports': True,
    'weather_metar': False,      # NOAA observations around the current map
    'weather_sigmet': False,     # NOAA aviation advisory polygons
    'sigmet_fill': True,        # discreet translucent SIGMET polygon interior
    'sigmet_colors': True,      # contour and symbol colors by NOAA phenomenon

    'ip_disclosure_accepted': False,  # saved consent; can be revoked in Preferences
    'monitor_favorites': True,     # check saved favorites while app is open
    'favorites_interval': 120,    # independent world-wide polling, seconds
    'notify_favorites': True,     # warn on plausible reappearance in flight
    'monitor_metar_favorites': True,  # poll saved airport / station METARs even in background
    'notify_metar_changes': True,     # notify only after a valid METAR baseline
    'monitor_emergencies': True,  # automatic worldwide checks while app is open
    'emergencies_interval': 120,  # three worldwide squawk calls per check
    'notify_emergencies': True,
    'sound_emergencies': False,  # system sound, if supported; never bypass mute
    'suggest_ip_fallback': True,  # Suggest a consent-based IP lookup when GeoClue is blocked
}

def load() -> dict:
    try:
        loaded = json.loads((CONFIG_DIR / 'settings.json').read_text('utf-8'))
        if not isinstance(loaded, dict):
            return DEFAULT.copy()
        settings = {**DEFAULT, **{k: v for k, v in loaded.items() if k in DEFAULT}}
        if loaded.get('language') == 'en_US' and loaded.get('language_schema') != 2:
            settings['language'] = 'auto'  # Old implicit default, not an explicit choice.
        if settings['language'] not in ('auto', 'en_US', 'pt_BR'):
            settings['language'] = 'auto'
        if settings['refresh'] not in INTERVALS:
            settings['refresh'] = 10  # migrate invalid legacy values
        if settings['refresh_background'] not in BACKGROUND_INTERVALS:
            settings['refresh_background'] = 10
        settings['autostart_login'] = autostart_enabled()
        if settings['marker_label'] not in ('off', 'registration', 'icao'):
            settings['marker_label'] = 'off'
        for key in ('favorites_interval', 'emergencies_interval'):
            if settings[key] not in (60, 120, 300, 600, 900):
                settings[key] = 120
        return settings
    except (OSError, ValueError, TypeError):
        settings = DEFAULT.copy()
        settings['autostart_login'] = autostart_enabled()
        return settings

def save(settings: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    new_file = CONFIG_DIR / 'settings.json.tmp'
    new_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + '\n', 'utf-8')
    new_file.replace(CONFIG_DIR / 'settings.json')

def cache_size() -> int:
    if not CACHE_DIR.exists():
        return 0
    return sum(p.stat().st_size for p in CACHE_DIR.rglob('*') if p.is_file())

def clear_cache() -> None:
    # Never delete shared Libshumate / GNOME Maps caches.
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
