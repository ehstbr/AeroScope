"""GNOME-like preferences dialog with a bottom icon view switcher."""
from .i18n import _
from gi.repository import Adw, Gtk
from .settings import cache_size
from .regional_poll import INTERVALS, BACKGROUND_INTERVALS, describe_interval


def _combo(title, subtitle, choices, selected, changed):
    row = Adw.ComboRow(title=title, subtitle=subtitle)
    row.set_model(Gtk.StringList.new(choices))
    row.set_selected(selected)
    row.connect('notify::selected', lambda obj, _prop: changed(obj.get_selected()))
    return row


def _switch(title, subtitle, enabled, changed):
    row = Adw.SwitchRow(title=title, subtitle=subtitle)
    row.set_active(enabled)
    row.connect('notify::active', lambda obj, _prop: changed(obj.get_active()))
    return row


class PreferencesWindow(Adw.Window):
    def sync_background_setting(self, key, value):
        if key == 'autostart_login' and hasattr(self, 'autostart_row'):
            self.autostart_row.set_active(bool(value))

    def sync_weather_setting(self, key, enabled):
        row = getattr(self, 'weather_rows', {}).get(key)
        if row is not None and row.get_active() != bool(enabled):
            row.set_active(bool(enabled))

    def sync_visual_setting(self, key, enabled):
        if key == 'marker_label':
            codes = ('off', 'registration', 'icao')
            if enabled in codes and hasattr(self, 'marker_label_row'):
                index = codes.index(enabled)
                if self.marker_label_row.get_selected() != index:
                    self.marker_label_row.set_selected(index)
            return
        if key == 'tower' and 'tower_sweep' in self.visual_rows:
            self.visual_rows['tower_sweep'].set_sensitive(bool(enabled))
        row = self.visual_rows.get(key)
        if row is not None and row.get_active() != bool(enabled):
            # Updating the UI may signal on_change; RadarWindow ignores identical values.
            row.set_active(bool(enabled))

    def __init__(self, parent, settings, on_change, on_clear_cache, on_clear_trails, on_ip_location=None):
        super().__init__(transient_for=parent, modal=True, title=_('Preferences — AeroScope'),
                         default_width=570, default_height=620)
        self.settings = settings
        self.on_change = on_change
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)
        toolbar.add_top_bar(Adw.HeaderBar())
        stack = Adw.ViewStack()
        toolbar.set_content(stack)
        # Same bottom-page navigation pattern as the user's other GNOME apps.
        bar = Adw.ViewSwitcherBar()
        bar.set_stack(stack)
        bar.set_reveal(True)
        toolbar.add_bottom_bar(bar)

        appearance = Adw.PreferencesPage()
        stack.add_titled_with_icon(appearance, 'appearance', _('Appearance'), 'applications-graphics-symbolic')
        general = Adw.PreferencesGroup(title=_('Application appearance'))
        appearance.add(general)
        options = [_('Automatic (system)'), _('Light'), _('Dark')]
        themes = ['system', 'light', 'dark']
        languages = [_('Automatic (system)'), 'English (United States)', 'Português (Brasil)']
        language_codes = ('auto', 'en_US', 'pt_BR')
        general.add(_combo(_('Language'),
                           _('Restart AeroScope to apply the selected language.'),
                           languages, language_codes.index(settings.get('language', 'auto')),
                           lambda idx: on_change('language', language_codes[idx])))
        general.add(_combo(_('Theme'), _('Follows the desktop appearance setting or uses your choice'),
                           options, themes.index(settings['theme']),
                           lambda idx: on_change('theme', themes[idx])))
        maps = Adw.PreferencesGroup(title=_('Map'), description=_('Free providers with visible attribution'))
        appearance.add(maps)
        sources = ['OpenStreetMap', 'OpenTopoMap-R', 'OpenHikingMap']
        names = ['osm', 'topo', 'hiking']
        maps.add(_combo(_('Map provider'), _('No API key; subject to provider terms'),
                        sources, names.index(settings['map']),
                        lambda idx: on_change('map', names[idx])))
        maps.add(_switch(_('Show nearby airports'),
                         _('Markers with names, codes and locations'),
                         settings['show_airports'], lambda val: on_change('show_airports', val)))
        visual = Adw.PreferencesGroup(title=_('Map display'),
                                      description=_('These shortcuts are also in the main menu.'))
        appearance.add(visual)
        self.visual_rows = {}
        for key, title, description in (
                ('tower', _('Control tower mode'),
                 _('Shows distance rings around the radar center')),
                ('clock_ring', _('Selected aircraft clock'),
                 _('12-hour ring relative to the aircraft heading, independent of tower mode')),
                ('tower_sweep', _('Rotating sweep'),
                 _('In tower mode, reveals previously received positions as the sweep passes, without new requests'))):
            row = _switch(title, description, settings[key],
                          lambda val, setting=key: on_change(setting, val))
            self.visual_rows[key] = row
            visual.add(row)
        self.visual_rows['tower_sweep'].set_sensitive(bool(settings['tower']))
        caption_choices = [_('Disabled'), _('Registration (ICAO24 if unavailable)'), 'ICAO24']
        caption_codes = ['off', 'registration', 'icao']
        self.marker_label_row = _combo(
            _('Labels next to aircraft icons'),
            _('Shows a small fixed label below every aircraft, including in the mini-map'),
            caption_choices,
            caption_codes.index(settings.get('marker_label', 'off')),
            lambda idx: on_change('marker_label', caption_codes[idx]))
        visual.add(self.marker_label_row)

        weather = Adw.PreferencesGroup(
            title='Meteorologia (opcional)',
            description=_('Layers also available under View → Weather. Advisory data; not a substitute for official flight information.'))
        appearance.add(weather)
        self.weather_rows = {}
        for key, title, subtitle in (
                ('weather_metar', _('Airport METAR reports · NOAA'),
                 _('Nearby aviation weather observations, every 15 min.')),
                ('weather_sigmet', _('SIGMET areas · NOAA'),
                 _('Outlines of active aviation weather advisories, every 15 min.'))):
            row = _switch(title, subtitle, settings[key],
                          lambda val, setting=key: on_change(setting, val))
            self.weather_rows[key] = row
            weather.add(row)
        for key, title, subtitle in (
                ('sigmet_fill', _('Show SIGMET area fill'),
                 _('10% translucent fill; 18% for the selected area, and subtler in tower mode.')),
                ('sigmet_colors', _('Use colors by SIGMET phenomenon'),
                 _('Distinct outlines and symbols for thunderstorms, icing, turbulence and other phenomena.'))):
            row = _switch(title, subtitle, settings.get(key, True),
                          lambda val, setting=key: on_change(setting, val))
            self.weather_rows[key] = row
            weather.add(row)

        flight = Adw.PreferencesPage()
        stack.add_titled_with_icon(flight, 'tracking', 'Radar', 'airplane-mode-symbolic')
        track = Adw.PreferencesGroup(title=_('Live tracking'),
                                     description=_('Actual ADSB.lol positions; optional visual animation between updates'))
        flight.add(track)
        delays = list(INTERVALS)
        track.add(_combo(_('Regional refresh — map open'),
                         _('Main window or mini-map visible. Default: 10 s; includes 2, 4, 8 and 10 minutes.'),
                         [describe_interval(x) for x in delays], delays.index(settings['refresh']),
                         lambda idx: on_change('refresh', delays[idx])))
        background_delays = list(BACKGROUND_INTERVALS)
        track.add(_combo(_('Regional refresh — tray only'),
                         _('Last viewed area. Disabled mode keeps only favorites and emergencies. Default: 10 s.'),
                         [describe_interval(x) for x in background_delays],
                         background_delays.index(settings['refresh_background']),
                         lambda idx: on_change('refresh_background', background_delays[idx])))
        track.add(_switch(_('Show startup preparation'),
                          _('Dims the window and waits for up to three initial updates, with a skip option'),
                          settings['startup_splash'],
                          lambda value: on_change('startup_splash', value)))
        track.add(_switch(_('Animate aircraft movement'),
                          _('Smooth movement towards the confirmed position until the next update'),
                          settings['animate_aircraft'],
                          lambda value: on_change('animate_aircraft', value)))
        track.add(_switch(_('Subtle altitude perspective'),
                          _('Cruising aircraft appear slightly larger than aircraft on the ground'),
                          settings['altitude_perspective'],
                          lambda value: on_change('altitude_perspective', value)))
        location_group = Adw.PreferencesGroup(
            title=_('Location'),
            description=_('AeroScope uses GeoClue when available on GNOME, KDE, XFCE and other desktops. If system location is unavailable, IP lookup is an approximate and optional alternative.'))
        flight.add(location_group)
        ip_row = Adw.ActionRow(title=_('Approximate IP location'),
                               subtitle=_('Queries only on request; IP explanation appears only on first authorization'))
        ip_button = Gtk.Button(label=_('Find my location'))
        ip_button.set_valign(Gtk.Align.CENTER)
        ip_button.set_sensitive(on_ip_location is not None)
        if on_ip_location is not None:
            ip_button.connect('clicked', lambda *_: on_ip_location())
        ip_row.add_suffix(ip_button)
        location_group.add(ip_row)
        location_group.add(_switch(
            _('Remember IP location authorization'),
            _('You may revoke previously granted permission; the next use will ask for confirmation'),
            settings.get('ip_disclosure_accepted', False),
            lambda value: on_change('ip_disclosure_accepted', value)))
        location_group.add(_switch(
            _('Suggest IP location when necessary'),
            _('If system location fails, offers an alternative without automatically checking the IP address'),
            settings.get('suggest_ip_fallback', True),
            lambda value: on_change('suggest_ip_fallback', value)))
        track.add(Adw.ActionRow(title=_('Geographic coverage'),
                                subtitle=_('Fixed 250 NM radius; reuses the area as the map moves.')))
        speeds = [_('Kilometers per hour (km/h)'), _('Knots (kt)'), _('Miles per hour (mph)')]
        codes = ['kmh', 'kt', 'mph']
        track.add(_combo(_('Primary speed unit'), _('All three units appear in the summary'),
                         speeds, codes.index(settings['speed']),
                         lambda idx: on_change('speed', codes[idx])))
        track.add(_switch(_('Hover summary'),
                          _('Shows summary information about an aircraft'),
                          settings['enable_hover'], lambda value: on_change('enable_hover', value)))
        track.add(_switch(_('Aircraft photos'),
                          _('Loads Planespotters thumbnails only when selected'),
                          settings['photos'], lambda value: on_change('photos', value)))
        track.add(_switch(_('Query flight history'),
                          _('Queries ADSB.aero only when an aircraft is selected'),
                          settings['history'], lambda value: on_change('history', value)))

        monitoring = Adw.PreferencesPage()
        stack.add_titled_with_icon(monitoring, 'monitor', 'Monitor', 'starred-symbolic')
        fav_group = Adw.PreferencesGroup(
            title=_('Favorite aircraft watchlist'),
            description=_('Worldwide checks while AeroScope is open or running in the background.'))
        monitoring.add(fav_group)
        fav_group.add(_switch(
            _('Automatically refresh favorites'),
            _('Checks favorite registrations even when the Visible tab is open'),
            settings['monitor_favorites'], lambda v: on_change('monitor_favorites', v)))
        monitor_delays = [60, 120, 300, 600, 900]
        fav_group.add(_combo(
            _('Favorite check interval'), _('Each favorite requires a request; keep API rate limits in mind'),
            [_('1 minute'), _('2 minutes'), _('5 minutes'), _('10 minutes'), _('15 minutes')],
            monitor_delays.index(settings['favorites_interval']),
            lambda idx: on_change('favorites_interval', monitor_delays[idx])))
        fav_group.add(_switch(
            _('Notify when detected in flight again'),
            _('Requires two previous checks without a signal; flight inferred from speed and altitude, not confirmed'),
            settings['notify_favorites'], lambda v: on_change('notify_favorites', v)))

        metar_group = Adw.PreferencesGroup(
            title=_('Favorite airport and station METARs'),
            description=_('Checks saved locations from NOAA every 15 minutes, including in the background.'))
        monitoring.add(metar_group)
        metar_group.add(_switch(
            _('Monitor favorite METARs automatically'),
            _('Batch checks, including saved locations outside the current map.'),
            settings.get('monitor_metar_favorites', True),
            lambda value: on_change('monitor_metar_favorites', value)))
        metar_group.add(_switch(
            _('Notify when a METAR bulletin changes'),
            _('The first valid observation sets a baseline; repeated or missing reports never alert.'),
            settings.get('notify_metar_changes', True),
            lambda value: on_change('notify_metar_changes', value)))

        alerts_group = Adw.PreferencesGroup(
            title=_('Worldwide emergencies'),
            description=_('Transponder codes 7700, 7600 and 7500. They do not prove a MAYDAY call.'))
        monitoring.add(alerts_group)
        alerts_group.add(_switch(
            _('Automatically monitor emergencies'),
            _('Enabled by default; uses three worldwide requests per update while the app is open'),
            settings['monitor_emergencies'], lambda v: on_change('monitor_emergencies', v)))
        alerts_group.add(_combo(
            _('Emergency check interval'), _('The API uses dynamic rate limits; HTTP 429 errors pause further requests'),
            [_('1 minute'), _('2 minutes'), _('5 minutes'), _('10 minutes'), _('15 minutes')],
            monitor_delays.index(settings['emergencies_interval']),
            lambda idx: on_change('emergencies_interval', monitor_delays[idx])))
        alerts_group.add(_switch(
            _('New emergency notifications'),
            _('Linux desktop notifications when a new code appears; the initial request does not trigger an alert'),
            settings['notify_emergencies'], lambda v: on_change('notify_emergencies', v)))
        alerts_group.add(_switch(
            _('Audible alarm'),
            _('Audible alert for new emergencies, respecting system sound and Do Not Disturb settings'),
            settings['sound_emergencies'], lambda v: on_change('sound_emergencies', v)))

        resident_group = Adw.PreferencesGroup(
            title=_('Window and background'),
            description=_('AeroScope continues requests and notifications while hidden. The system tray icon depends on desktop support.'))
        monitoring.add(resident_group)
        self.autostart_row = _switch(
            _('Start automatically at login'),
            _('Start in tray without opening the map or running regional requests until first use. Favorites and emergencies remain monitored; requires a compatible tray icon.'),
            settings.get('autostart_login', False), lambda v: on_change('autostart_login', v))
        resident_group.add(self.autostart_row)
        resident_group.add(_switch(
            _('Continue monitoring when window closes'),
            _('Keeps the app running in the background; the tray icon menu has a Quit option. If no icon is available, a confirmation will appear.'),
            settings['background_on_close'], lambda v: on_change('background_on_close', v)))
        resident_group.add(_switch(
            _('Mini-map always on top (when supported)'),
            _('Enabled by default: requests always-on-top in X11. On GNOME/Wayland, use your window manager settings to keep the window above others.'),
            settings.get('pip_always_on_top', True),
            lambda v: on_change('pip_always_on_top', v)))
        resident_group.add(_switch(
            _('Show mini-map when closing'),
            _('Shows only the map and aircraft, with controls to expand or return to the main window. Stacking above other windows depends on the compositor.'),
            settings['close_to_pip'], lambda v: on_change('close_to_pip', v)))

        storage = Adw.PreferencesPage()
        stack.add_titled_with_icon(storage, 'storage', _('Storage'), 'drive-harddisk-symbolic')
        st = Adw.PreferencesGroup(title=_('Local data'),
                                  description=_('Tracks and history are kept only in memory during the session.'))
        storage.add(st)
        self.usage = Adw.ActionRow(title=_('AeroScope temporary files'),
                                   subtitle=self._cache_text())
        st.add(self.usage)
        clear_button = Gtk.Button(label=_('Clear cache'))
        clear_button.set_valign(Gtk.Align.CENTER)
        clear_button.add_css_class('destructive-action')
        clear_button.connect('clicked', lambda *_: self._clear(on_clear_cache))
        self.usage.add_suffix(clear_button)
        trailrow = Adw.ActionRow(title=_('Live track'),
                                 subtitle=_('Discards all positions recorded during this session'))
        trail_btn = Gtk.Button(label=_('Clear tracks'))
        trail_btn.set_valign(Gtk.Align.CENTER)
        trail_btn.connect('clicked', lambda *_: on_clear_trails())
        trailrow.add_suffix(trail_btn)
        st.add(trailrow)
        note = Adw.PreferencesGroup(title=_('Map cache'),
             description=_("Libshumate maintains its own tile cache according to each provider's rules. AeroScope does not delete caches shared with other GNOME applications."))
        storage.add(note)

        info = Adw.PreferencesPage()
        stack.add_titled_with_icon(info, 'info', _('Information'), 'dialog-information-symbolic')
        about = Adw.PreferencesGroup(title=_('About the data'),
            description=_('ADSB.lol: current positions. ADSB.aero: archived history. Planespotters.net: contributor photos. OpenStreetMap/OpenTopoMap: maps. This application is not intended for aeronautical navigation.'))
        info.add(about)

    def _cache_text(self):
        return _('{value0:.2f} MB of temporary metadata').format(value0=cache_size() / 1024 / 1024)

    def _clear(self, handler):
        handler()
        self.usage.set_subtitle(self._cache_text())
