"""Native GNOME watchlist and global transponder-status window."""
from __future__ import annotations
from .i18n import _
from .data import AIRPORTS
from .airport_weather_badge import metar_badge
from .favorite_search import favorite_candidates, FavoriteCandidate
from .weather_data import Metar, fetch_metar_station

import logging
import re
import time

from gi.repository import Gtk, GLib, Pango

from .monitor import (ALERT_CODES, add_favorite, fetch_favorite,
                      fetch_global_emergencies, save_favorites, live_favorite_checks)
from .data import RateLimitError
from .monitor_alerts import AlertTransitions
from .emergency_history import SessionEmergencyHistory, observed_at
from .favorite_history import SessionFavoriteHistory
from .residency import can_monitor_in_background
from .sidebar_counts import airborne_favorites_count, tab_label
from .sidebar_layout import needs_wrap, MONITOR_NATURAL_WIDTH_CHARS

LOG = logging.getLogger('aeroscope.monitor')


def _label(text, style=None, wrap=False):
    label = Gtk.Label(label=str(text), xalign=0)
    # Favorites, global alerts and ended history all share this bounded
    # component. A long callsign, error or status can never widen the pane.
    if needs_wrap(text, wrap):
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_width_chars(1)
        label.set_max_width_chars(MONITOR_NATURAL_WIDTH_CHARS)
    else:
        label.set_wrap(False)
    if style:
        label.add_css_class(style)
    return label


def _clear(box):
    item = box.get_first_child()
    while item is not None:
        following = item.get_next_sibling()
        box.remove(item)
        item = following


class SidebarMonitor:
    """Sidebar pages; query only on visit or every 120 seconds while active.

    Uses the same endpoints as the old monitor window, but does not create
    another toplevel window or independently poll when hidden.
    """
    def __init__(self, radar, stack):
        self.radar = radar
        self.switch = stack
        self._alive = True
        self._busy_fav = False
        self._busy_global = False
        self._station_search_busy = False
        self._station_search_request = 0
        self._last_fav_request = 0.0
        self._last_global_request = 0.0
        self._cooldown_until = 0.0
        self._fav_status = {}
        self._favorite_history = SessionFavoriteHistory()
        self._global_rows = []
        self._global_errors = {}
        self._global_checked_at = 0.0
        self._emergency_history = SessionEmergencyHistory()
        # One startup snapshot is always requested, independent of which tab
        # is visible and of the user's preference for *periodic* monitoring.
        self._startup_started = False
        self._startup_pending = False
        self._startup_favorites_scheduled = False
        self._transitions = AlertTransitions()
        self._build()
        self.switch.connect('notify::visible-child-name', self._changed_tab)
        GLib.timeout_add_seconds(5, self._auto_refresh)

    def _build(self):
        favorites = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        favorites.set_margin_start(16)
        favorites.set_margin_end(16)
        favorites.set_margin_top(12)
        favorites.set_margin_bottom(12)
        # The tab already identifies this page. Keep only its useful actions.
        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_entry = Gtk.Entry(placeholder_text=_('Aircraft, airport, or METAR station…'))
        self.add_entry.set_hexpand(True)
        self.add_entry.connect('activate', self._add)
        self.add_entry.connect('changed', self._search_favorites_changed)
        add_row.append(self.add_entry)
        add_button = Gtk.Button(label=_('Add or search'))
        self.add_button = add_button
        add_button.add_css_class('suggested-action')
        add_button.connect('clicked', self._add)
        add_row.append(add_button)
        # Inline results, like the main search: no event-stealing popover.
        self.add_results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        results_scroll = Gtk.ScrolledWindow()
        results_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        results_scroll.set_max_content_height(200)
        results_scroll.set_propagate_natural_height(True)
        results_scroll.set_child(self.add_results)
        self.add_form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_form.append(add_row)
        self.add_form.append(results_scroll)
        self.add_revealer = Gtk.Revealer()
        self.add_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.add_revealer.set_transition_duration(170)
        self.add_revealer.set_reveal_child(False)
        self.add_revealer.set_child(self.add_form)
        favorites.append(self.add_revealer)
        cmd = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.fav_message = _label(_('Search aircraft, airports and stations; 12-aircraft limit.'), wrap=True)
        self.fav_message.add_css_class('dim-label')
        self.fav_message.set_hexpand(True)
        # Three action buttons share this row; the status wraps vertically.
        self.fav_message.set_max_width_chars(18)
        cmd.append(self.fav_message)
        plus = Gtk.Button(icon_name='list-add-symbolic')
        plus.add_css_class('flat')
        plus.set_tooltip_text(_('Search aircraft, airports or METAR stations to add to favorites'))
        plus.connect('clicked', self._toggle_add_form)
        cmd.append(plus)
        self.refresh_fav_btn = Gtk.Button(icon_name='view-refresh-symbolic')
        self.refresh_fav_btn.set_tooltip_text(_('Check favorites now'))
        self.refresh_fav_btn.connect('clicked', self._refresh_all_favorites)
        cmd.append(self.refresh_fav_btn)
        self.show_favorite_history = Gtk.ToggleButton()
        self.show_favorite_history.set_icon_name('document-open-recent-symbolic')
        self.show_favorite_history.add_css_class('flat')
        self.show_favorite_history.add_css_class('emergency-history-button')
        self.show_favorite_history.set_tooltip_text(
            _('Show/hide favorite observation history for this session'))
        self.show_favorite_history.set_active(False)
        self.show_favorite_history.connect('toggled', lambda *_: self._render_favorites())
        cmd.append(self.show_favorite_history)
        favorites.append(cmd)
        fav_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.fav_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fav_scroll.set_child(self.fav_list)
        favorites.append(fav_scroll)
        self.favorites_stack_page = self.switch.add_titled(
            favorites, 'favorites', tab_label(_('Favorites'), 0 if not self.radar.favorites else None))

        world = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        world.set_margin_start(16)
        world.set_margin_end(16)
        world.set_margin_top(12)
        world.set_margin_bottom(12)
        expl = _label(_('Worldwide codes 7700, 7600 and 7500. They do not confirm MAYDAY.'), wrap=True)
        expl.add_css_class('dim-label')
        world.append(expl)
        world_cmd = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.global_message = _label(_('Not checked yet.'), wrap=True)
        self.global_message.set_hexpand(True)
        self.global_message.set_max_width_chars(22)
        world_cmd.append(self.global_message)
        self.refresh_em_btn = Gtk.Button(icon_name='view-refresh-symbolic')
        self.refresh_em_btn.set_tooltip_text(_('Search worldwide codes now'))
        self.refresh_em_btn.connect('clicked', lambda *_: self._refresh_emergencies(force=True))
        world_cmd.append(self.refresh_em_btn)
        self.show_emergency_history = Gtk.ToggleButton()
        self.show_emergency_history.set_icon_name('document-open-recent-symbolic')
        self.show_emergency_history.add_css_class('flat')
        self.show_emergency_history.add_css_class('emergency-history-button')
        self.show_emergency_history.set_tooltip_text(
            _('Show/hide session emergency history; these are not official timestamps'))
        self.show_emergency_history.set_active(False)
        self.show_emergency_history.connect('toggled', lambda *_: self._render_emergencies())
        world_cmd.append(self.show_emergency_history)
        world.append(world_cmd)
        globe_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.global_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        globe_scroll.set_child(self.global_list)
        world.append(globe_scroll)
        self.emergencies_stack_page = self.switch.add_titled(
            world, 'emergencies', tab_label(_('Emergencies'), None))
        self._render_favorites()

    def _recent_live_checks(self):
        """Only reuse a recent *successful* radar snapshot.

        A plane leaving the 250 NM coverage is not marked offline. Its global
        monitoring continues independently of the current map position.
        """
        stamp = getattr(self.radar, '_last_live_snapshot_at', 0.0)
        if not stamp or time.time() - stamp > max(30, min(90, 2 * self.radar.poll_seconds + 15)):
            return {}
        return live_favorite_checks(self.radar.favorites, self.radar.records.values())

    def update_from_live(self, planes):
        """Apply current radar records to the favorites panel immediately.

        Called on the GTK main loop, from every successful regional radar
        refresh and whenever a user stars a plane. No HTTP call is made here.
        """
        checks = live_favorite_checks(self.radar.favorites, planes)
        if not checks:
            return
        # A recent live fix overrides an older global result, including an
        # 'offline' or error result, without changing unrelated favorites.
        self._fav_status.update(checks)
        self._favorite_history.observe(checks, {fav.key: fav for fav in self.radar.favorites})
        newly_flying = self._transitions.favorites_updated(checks)
        self._announce_favorite_flights(newly_flying)
        if self.switch.get_visible_child_name() == 'favorites':
            self._render_favorites()
        else:
            self._update_favorites_tab_title()

    def _announce_favorite_flights(self, newly_flying):
        if not self.radar.settings['notify_favorites']:
            return
        for key, plane in newly_flying:
            self.radar.emit_monitor_alert(
                _('Favorite aircraft detected in possible flight'),
                _('{value0} · {value1} · position received from ADSB.lol').format(value0=plane.registration or plane.flight or plane.hex.upper(), value1=plane.speed),
                notification_id='favorite-' + key.replace(':', '-'),
                action='app.monitor', sound=False)

    def _toggle_add_form(self, *_):
        expanded = not self.add_revealer.get_reveal_child()
        self.add_revealer.set_reveal_child(expanded)
        if expanded:
            self.add_entry.grab_focus()

    def start_initial_checks(self):
        """Start background monitoring during the radar warm-up.

        Worldwide squawk lookups run first (three server-side filters, not a
        world scan). Favorites follow after that request finishes. This avoids
        a burst of simultaneous requests on top of the first radar samples.
        Neither query is required for dismissing the splash screen.
        """
        if not self._alive or self.radar.demo or self._startup_started:
            return GLib.SOURCE_REMOVE
        self._startup_started = True
        self._startup_pending = True
        LOG.info(_('Warm-up: starting worldwide emergency check'))
        if self._busy_global:
            # A manual tab refresh started just before the warm-up hook.
            # Its callback will continue with the favorites lookup.
            return GLib.SOURCE_REMOVE
        if self._global_checked_at:
            self._queue_startup_favorites()
        elif not self._refresh_emergencies(force=True):
            # Backoff / error: do not spin, and never block the radar splash.
            self._queue_startup_favorites()
        return GLib.SOURCE_REMOVE

    def _queue_startup_favorites(self):
        if not self._startup_pending or self._startup_favorites_scheduled:
            return
        self._startup_favorites_scheduled = True
        GLib.timeout_add(850, self._start_startup_favorites)

    def _start_startup_favorites(self):
        self._startup_pending = False
        if self._alive and not self.radar.demo and self.radar.favorites:
            LOG.info(_('Warm-up: checking favorites not yet covered by the radar'))
            self._refresh_favorites(force=True)
        return GLib.SOURCE_REMOVE

    def _changed_tab(self, *_):
        # Do not launch competing background lookups while the initial
        # staggered checks are underway. The refresh buttons still work.
        if self._startup_pending:
            return
        active = self.switch.get_visible_child_name()
        if active == 'favorites' and not self._fav_status:
            self._refresh_favorites()
        elif active == 'emergencies' and not self._global_checked_at:
            self._refresh_emergencies()

    def _local_favorite_candidates(self, query):
        weather = getattr(self.radar, 'weather', None)
        local_stations = (weather.noaa[0] if weather is not None and weather.noaa else [])
        return favorite_candidates(query, self.radar.records.values(), AIRPORTS,
                                   local_stations)

    def _search_favorites_changed(self, *_args):
        _clear(self.add_results)
        query = self.add_entry.get_text().strip()
        if not query:
            return
        candidates = self._local_favorite_candidates(query)
        current_section = None
        titles = {'aircraft': _('Aircraft'), 'airport': _('Airports'),
                  'station': _('METAR stations')}
        for item in candidates:
            if item.kind != current_section:
                current_section = item.kind
                heading = _label(titles[item.kind], 'dim-label')
                heading.set_margin_top(5)
                self.add_results.append(heading)
            button = Gtk.Button()
            button.add_css_class('flat')
            button.set_tooltip_text(_('Add to favorites'))
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = _label(item.title, wrap=True)
            title.add_css_class('heading')
            content.append(title)
            subtitle = _label(item.subtitle, 'dim-label', wrap=True)
            content.append(subtitle)
            button.set_child(content)
            button.connect('clicked', lambda *_args, match=item: GLib.idle_add(
                self._select_candidate_idle, match))
            self.add_results.append(button)
        if re.fullmatch(r'[A-Z0-9]{4}', query.upper()) and not any(
                result.kind in ('airport', 'station') and
                (result.key == query.upper() or result.subtitle == query.upper())
                for result in candidates):
            self.add_results.append(_label(
                _('Four-character ICAO code: press Enter to check the NOAA station.'),
                'dim-label', wrap=True))

    def _select_candidate_idle(self, candidate):
        # The selected result button may be removed after choosing it. Wait
        # until GTK has returned from its `clicked` signal before rebuilding.
        if self._alive:
            self._add_candidate(candidate)
        return GLib.SOURCE_REMOVE

    def _finish_add(self):
        self.add_entry.set_text('')
        self.add_revealer.set_reveal_child(False)

    def _add_candidate(self, candidate: FavoriteCandidate):
        if candidate.kind == 'airport':
            if candidate.key in self.radar.favorite_airports:
                self.fav_message.set_text(_('This airport is already in favorites.'))
                return
            self.radar._toggle_airport_favorite(candidate.key)
            if candidate.key in self.radar.favorite_airports:
                self._finish_add()
            return
        if candidate.kind == 'station':
            if candidate.key in self.radar.favorite_stations:
                self.fav_message.set_text(_('This station is already in favorites.'))
                return
            if candidate.lat is None or candidate.lon is None:
                self.fav_message.set_text(_('This station has no known location.'))
                return
            self._save_station_candidate(candidate.key, candidate.lat, candidate.lon)
            return
        # Selected aircraft from the live radar: prefer registration, falling
        # back to ICAO24, the same policy as starring a map marker.
        try:
            updated = add_favorite(self.radar.favorites, candidate.aircraft_kind,
                                   candidate.key, candidate.title)
            if updated == self.radar.favorites:
                self.fav_message.set_text(_('This aircraft is already in favorites.'))
                return
            save_favorites(updated)
        except (OSError, ValueError) as exc:
            self.fav_message.set_text(str(exc))
            return
        self.radar.favorites = updated
        self._finish_add()
        self.radar._favorites_changed()
        self._last_fav_request = 0.0
        self._refresh_favorites(force=True)

    def _save_station_candidate(self, code, lat, lon):
        # Coordinate data come from an actual NOAA observation, not from the
        # arbitrary ICAO string or a hard-coded location guess.
        try:
            if not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
                raise ValueError(_('Invalid station location'))
        except (TypeError, ValueError):
            self.fav_message.set_text(_('This station has no known location.'))
            return
        report = Metar(code, float(lat), float(lon), '', 'N/D', '', {})
        self.radar._toggle_station_favorite(report)
        if code in self.radar.favorite_stations:
            self._finish_add()

    def _add(self, *_args):
        if self._station_search_busy:
            return
        term = self.add_entry.get_text().strip().upper()
        if not term:
            return
        matches = self._local_favorite_candidates(term)
        # Exact IATA, ICAO or NOAA station code takes precedence over a
        # registration lookup. Otherwise choose from the visible suggestions.
        airports = [m for m in matches if m.kind == 'airport' and
                    term in (m.key, m.subtitle)]
        if airports:
            self._add_candidate(airports[0])
            return
        stations = [m for m in matches if m.kind == 'station' and term == m.key]
        if stations:
            self._add_candidate(stations[0])
            return
        # A matching radar aircraft takes precedence over an ICAO-station lookup.
        planes = [m for m in matches if m.kind == 'aircraft' and term == m.key]
        if planes:
            self._add_candidate(planes[0])
            return
        if re.fullmatch(r'[A-Z0-9]{4}', term):
            self._station_search_busy = True
            self.add_button.set_sensitive(False)
            self.fav_message.set_text(_('Checking NOAA METAR station…'))
            self._station_search_request += 1
            request = self._station_search_request
            self.radar._async(lambda: fetch_metar_station(term),
                              lambda report, error: self._station_search_done(
                                  term, request, report, error))
            return
        if not re.fullmatch(r'[A-Z0-9]{6}|[A-Z0-9][A-Z0-9\-]{1,11}', term):
            self.fav_message.set_text(_('Choose an airport, aircraft or station from the results.'))
            return
        # Long name searches must not silently become aircraft registrations.
        if len(term) > 6 and '-' not in term and not any(ch.isdigit() for ch in term):
            self.fav_message.set_text(_('Choose a result from the list.'))
            return
        candidate = FavoriteCandidate('aircraft', term, term, '',
                                      aircraft_kind=('icao' if re.fullmatch(r'[0-9A-F]{6}', term)
                                                     else 'registration'))
        self._add_candidate(candidate)

    def _station_search_done(self, code, request, report, error):
        if not self._alive or request != self._station_search_request:
            return
        self._station_search_busy = False
        self.add_button.set_sensitive(True)
        if error is not None:
            self.fav_message.set_text(
                _('Could not check NOAA station: {value0}').format(value0=error))
        elif report is None:
            self.fav_message.set_text(_('No current NOAA METAR for this ICAO station.'))
        elif report.lat == 0.0 and report.lon == 0.0:
            self.fav_message.set_text(_('NOAA did not provide this station location.'))
        elif code in self.radar.favorite_stations:
            self.fav_message.set_text(_('This station is already in favorites.'))
        else:
            self._save_station_candidate(code, report.lat, report.lon)

    def _remove(self, key):
        updated = [f for f in self.radar.favorites if f.key != key]
        try:
            save_favorites(updated)
            self.radar.favorites = updated
            self._fav_status.pop(key, None)
            self._favorite_history.remove(key, time.time())
            self._transitions.remove_favorite(key)
            self._render_favorites()
            self.radar._favorites_changed()
        except OSError as exc:
            self.fav_message.set_text(_('Could not save: {value0}').format(value0=exc))

    def _update_favorites_tab_title(self):
        # A global hit is not a takeoff. Count only positions reasonably
        # compatible with flight, never aircraft on the ground or offline.
        count = airborne_favorites_count(self.radar.favorites, self._fav_status)
        if self.radar.favorites and not self._fav_status:
            count = None  # No verification yet: do not claim zero in flight.
        self.favorites_stack_page.set_title(tab_label(_('Favorites'), count))

    def _update_emergencies_tab_title(self):
        # Unknown until an actual global lookup succeeds; failures do not
        # imply that the sky is clear of emergencies.
        count = len(self._global_rows) if self._global_checked_at else None
        active = bool(count and count > 0)
        self.emergencies_stack_page.set_title(
            tab_label(_('● Emergencies') if active else _('Emergencies'), count))
        # The GNOME StackSwitcher gets a restrained danger color only while
        # one or more codes are active. The title dot is also visible in
        # environments that override the theme's CSS.
        tabs = getattr(self.radar, 'sidebar_tabs', None)
        if tabs is not None:
            if active:
                tabs.add_css_class('emergency-attention')
            else:
                tabs.remove_css_class('emergency-attention')

    def _render_favorites(self):
        self._update_favorites_tab_title()
        _clear(self.fav_list)
        if not self.radar.favorites and not self.radar.favorite_airports and not self.radar.favorite_stations:
            self.fav_list.append(_label(_('No favorites yet. Star an aircraft, airport or METAR station on the map.'), wrap=True))
            # Keep the ended session history available after removing favorites.
        for fav in self.radar.favorites:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.add_css_class('card')
            box.set_margin_bottom(2)
            box.set_margin_top(2)
            box.set_margin_start(3)
            box.set_margin_end(6)
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            left.set_margin_start(10)
            left.set_margin_top(10)
            left.set_margin_bottom(10)
            left.set_hexpand(True)
            left.append(_label(fav.label or fav.value, 'heading', wrap=True))
            state, aircraft, checked_at, callsign = self._fav_status.get(fav.key, ('unknown', None, None, ''))
            label = {'active': _('Currently tracked'), 'active-no-position': _('Detected, no recent position'),
                     'offline': _('No recent signal'), 'error': _('Could not verify'),
                     'unknown': _('Not checked yet')}.get(state, _('Unknown status'))
            if aircraft is not None:
                label += f' · {aircraft.flight or aircraft.model or aircraft.hex.upper()}'
            elif callsign:
                label += ' · ' + callsign
            if checked_at:
                label += ' · ' + time.strftime('%H:%M:%S', time.localtime(checked_at))
            detail = _label(label, wrap=True)
            if state in ('active', 'active-no-position'):
                detail.add_css_class('success')
            else:
                detail.add_css_class('dim-label')
            left.append(detail)
            box.append(left)
            if aircraft is not None:
                show = Gtk.Button(icon_name='find-location-symbolic')
                show.set_tooltip_text(_('Show aircraft on map'))
                show.set_valign(Gtk.Align.CENTER)
                show.connect('clicked', lambda *_a, p=aircraft: self._show_aircraft(p))
                box.append(show)
            remove = Gtk.Button(icon_name='edit-delete-symbolic')
            remove.set_tooltip_text(_('Remove favorite'))
            remove.set_valign(Gtk.Align.CENTER)
            remove.set_margin_end(10)  # Never touch the right edge of the card.
            remove.connect('clicked', lambda *_a, key=fav.key: self._remove(key))
            box.append(remove)
            self.fav_list.append(box)
        airports = sorted(code for code in self.radar.favorite_airports if code in AIRPORTS)
        stations = sorted(self.radar.favorite_stations)
        if airports:
            title = _label(_('Favorite airports'), 'heading')
            title.set_margin_top(8)
            self.fav_list.append(title)
        for code in airports:
            icao, name, lat, lon = AIRPORTS[code]
            self._render_metar_favorite(code, icao, name, is_airport=True)
        if stations:
            title = _label(_('Favorite weather stations'), 'heading')
            title.set_margin_top(8)
            self.fav_list.append(title)
        for code in stations:
            self._render_metar_favorite(code, code, _('Weather station'), is_airport=False)
        if self.show_favorite_history.get_active():
            ended = self._favorite_history.ended()
            if ended:
                heading = _label(_('Favorite observation history'), 'heading')
                heading.set_margin_top(10)
                self.fav_list.append(heading)
            else:
                note = _label(_('No previous changes recorded during this session.'), wrap=True)
                note.add_css_class('dim-label')
                self.fav_list.append(note)
            for entry in ended:
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row.add_css_class('card')
                row.add_css_class('emergency-history-ended')
                row.set_margin_start(3)
                row.set_margin_end(8)
                row.set_margin_top(2)
                row.set_margin_bottom(2)
                name = _label(f'{entry["name"]} · {entry["description"]}', 'heading', wrap=True)
                name.set_margin_start(10)
                name.set_margin_top(8)
                row.append(name)
                times = _label(
                    _('Detected: ') + observed_at(entry['first_seen']) +
                    _('\nObserved change: ') + observed_at(entry['ended_at']), wrap=True)
                times.add_css_class('dim-label')
                times.set_margin_start(10)
                times.set_margin_end(10)
                times.set_margin_bottom(8)
                row.append(times)
                self.fav_list.append(row)

    def _render_metar_favorite(self, display_code, icao, name, is_airport):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.add_css_class('card')
        card.set_margin_start(3)
        card.set_margin_end(6)
        card.set_margin_top(2)
        card.set_margin_bottom(2)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        info.set_margin_start(10)
        info.set_margin_top(10)
        info.set_margin_bottom(10)
        info.set_hexpand(True)
        info.append(_label(f'{display_code} · {name}', 'heading', wrap=True))
        info.append(_label(_('ICAO station: {value0}').format(value0=icao), 'dim-label', wrap=True))
        weather = getattr(self.radar, 'weather', None)
        state, report, error = (weather.favorite_metar_status(icao) if weather is not None
                                else ('loading', None, None))
        if report is not None:
            # Only the official NOAA flight category (if available) appears in
            # the compact Favorites list. Full METAR remains in the inspector.
            category = metar_badge(report)
            if category is not None:
                badge = Gtk.Label(label=category)
                badge.add_css_class('metar-favorite-category')
                badge.add_css_class('metar-' + category.lower())
                if category == 'METAR':
                    badge.set_tooltip_text(_('METAR available; flight category not provided'))
                else:
                    badge.set_tooltip_text(_('Flight category from the latest NOAA METAR'))
                badge.set_halign(Gtk.Align.START)
                info.append(badge)
            else:
                info.append(_label(_('Flight category unavailable'), 'dim-label'))
            observed = report.observed or _('time not provided')
            info.append(_label(_('Observed: {value0}').format(value0=observed),
                               'dim-label', wrap=True))
            if state == 'error':
                info.append(_label(_('Could not refresh METAR; showing the last available report.'),
                                   'dim-label', wrap=True))
        else:
            status = (_('Checking METAR…') if state == 'loading' else
                      _('METAR temporarily unavailable.') if state == 'error' else
                      _('No recent METAR available.') if state == 'missing' else
                      _('Waiting for the first METAR check.'))
            info.append(_label(status, 'dim-label', wrap=True))
        # SIGMET is independent of METAR availability or flight category.
        if weather is not None:
            position = (AIRPORTS[display_code][2:4] if is_airport
                        else self.radar.favorite_stations.get(icao))
            if position is not None:
                sigmet_state, advisories = weather.sigmet_coverage(*position)
                if advisories:
                    from .sigmet_readable import describe_sigmet
                    for advisory in advisories[:2]:
                        decoded = describe_sigmet(advisory)
                        warning = _label('⚠ ' + decoded.title, wrap=True)
                        warning.add_css_class('dashboard-sigmet-title')
                        warning.set_tooltip_text(advisory.text or decoded.description)
                        info.append(warning)
                    if len(advisories) > 2:
                        info.append(_label(_('+ {value0} more SIGMET advisories').format(
                            value0=len(advisories) - 2), 'dim-label'))
                elif sigmet_state == 'error' and report is None:
                    info.append(_label(_('SIGMET verification unavailable.'),
                                       'dim-label', wrap=True))
        # The information area opens the same inspector used by the map.
        # The two adjacent action buttons remain independent of this click.
        info.set_cursor_from_name('pointer')
        info.set_tooltip_text(_('Show airport details') if is_airport else
                              _('Show weather station details'))
        inspect_click = Gtk.GestureClick.new()
        inspect_click.set_button(1)
        if is_airport:
            inspect_click.connect('released', lambda *_args, airport=display_code:
                                  self.radar.select_airport(airport))
        else:
            from .weather_data import Metar
            pos = self.radar.favorite_stations.get(icao, (0., 0.))
            inspected_metar = report or Metar(icao, *pos, '', '', '', {})
            inspect_click.connect('released', lambda *_args, m=inspected_metar:
                                  self.radar.select_weather_station(m))
        info.add_controller(inspect_click)
        card.append(info)
        locate = Gtk.Button(icon_name='find-location-symbolic')
        locate.set_valign(Gtk.Align.CENTER)
        locate.set_tooltip_text(_('Center airport on map') if is_airport else
                                _('Center weather station on map'))
        if is_airport:
            locate.connect('clicked', lambda *_args, airport=display_code:
                           self.radar._center_airport(airport))
        else:
            locate.connect('clicked', lambda *_args, station=icao:
                           self.radar._center_station(station))
        card.append(locate)
        remove = Gtk.Button(icon_name='edit-delete-symbolic')
        remove.set_valign(Gtk.Align.CENTER)
        remove.set_margin_end(10)
        remove.set_tooltip_text(_('Remove airport from favorites') if is_airport else
                                _('Remove station from favorites'))
        if is_airport:
            remove.connect('clicked', lambda *_args, airport=display_code:
                           self.radar._toggle_airport_favorite(airport))
        else:
            from .weather_data import Metar
            pos = self.radar.favorite_stations.get(icao, (0., 0.))
            row_metar = report or Metar(icao, *pos, '', 'N/D', '', {})
            remove.connect('clicked', lambda *_args, m=row_metar:
                           self.radar._toggle_station_favorite(m))
        card.append(remove)
        self.fav_list.append(card)

    def _render_emergencies(self):
        self._update_emergencies_tab_title()
        _clear(self.global_list)
        if not self._global_rows:
            if self._global_errors:
                self.global_list.append(_label(_('Incomplete lookup: some codes failed. Cannot guarantee absence of alerts.'), wrap=True))
            elif self._global_checked_at:
                self.global_list.append(_label(_('No emergency transmissions in the latest check.'), wrap=True))
        for entry in self._global_rows:
            area = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            area.add_css_class('card')
            area.set_margin_top(2)
            area.set_margin_bottom(2)
            area.set_margin_start(3)
            area.set_margin_end(3)
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            column.set_hexpand(True)
            column.set_margin_start(10)
            column.set_margin_top(10)
            column.set_margin_bottom(10)
            title = _label((entry['flight'] or entry['registration'] or entry['hex'].upper())
                           + f" · {entry['squawk']}", 'heading', wrap=True)
            column.append(title)
            subtitle = entry['description']
            if entry['registration']:
                subtitle += ' · ' + entry['registration']
            if entry['aircraft'] is None:
                subtitle += _(' · no recent position')
            column.append(_label(subtitle, wrap=True))
            area.append(column)
            if entry['aircraft'] is not None:
                locate = Gtk.Button(icon_name='find-location-symbolic')
                locate.set_tooltip_text(_('Center aircraft on map'))
                locate.set_valign(Gtk.Align.CENTER)
                locate.set_margin_end(13)  # inset within the emergency card
                locate.connect('clicked', lambda *_a, p=entry['aircraft']: self._show_aircraft(p))
                area.append(locate)
            self.global_list.append(area)
        if self.show_emergency_history.get_active():
            ended = self._emergency_history.ended()
            if ended:
                heading = _label(_('Resolved alerts during monitoring'), 'heading')
                heading.set_margin_top(8)
                self.global_list.append(heading)
            else:
                self.global_list.append(_label(_('No resolved alerts in this session yet.'), wrap=True))
            for record in ended[:100]:
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row.add_css_class('card')
                row.add_css_class('emergency-history-ended')
                row.set_margin_start(3)
                row.set_margin_end(8)
                row.set_margin_top(2)
                row.set_margin_bottom(2)
                code = record['squawk']
                ident = record.get('flight') or record.get('registration') or record['hex'].upper()
                label = _label(_('{value0} · {value1} · no emergency signal').format(value0=ident, value1=code), 'heading', wrap=True)
                label.set_margin_start(10)
                label.set_margin_top(8)
                row.append(label)
                times = _label(_('Detected: ') + observed_at(record['first_seen']) +
                               _('\nNo longer detected: ') + observed_at(record['no_longer_seen']),
                               wrap=True)
                times.add_css_class('dim-label')
                times.set_margin_start(10)
                times.set_margin_end(10)
                times.set_margin_bottom(8)
                row.append(times)
                self.global_list.append(row)

    def _show_aircraft(self, aircraft):
        # A worldwide squawk hit can be outside the regional 250 NM feed.
        # The main map retains a temporary selected marker and details until
        # the regional request catches up; never switch to Visíveis here.
        # A plane already present in the regional radar can reuse the smooth
        # pan used by selecting it on the map. Preserve the current zoom.
        # A distant favorite still needs the worldwide-to-regional transition
        # (which animates both the camera position and zoom).
        if aircraft.hex in self.radar.records:
            self.radar.select_plane(aircraft.hex)
        else:
            self.radar.focus_global_aircraft(aircraft)

    def _refresh_all_favorites(self, *_):
        self._refresh_favorites(force=True)
        self.radar.weather.refresh_favorite_metars(force=True)

    def _refresh_favorites(self, force=False):
        if self._busy_fav or not self._alive or not self.radar.favorites:
            self._render_favorites()
            return
        now = time.monotonic()
        if now < self._cooldown_until or now < getattr(self.radar, '_cooldown_until', 0):
            self.fav_message.set_text(_('API rate limit: waiting before next request.'))
            return
        interval = self.radar.settings.get('favorites_interval', 120)
        if now - self._last_fav_request < (25 if force else interval):
            return
        self._last_fav_request = now
        self._busy_fav = True
        self.refresh_fav_btn.set_sensitive(False)
        self.fav_message.set_text(_('Checking aircraft worldwide…'))
        live_checks = self._recent_live_checks()
        if live_checks:
            self.update_from_live(self.radar.records.values())
        favorites = [fav for fav in self.radar.favorites if fav.key not in live_checks]
        if not favorites:
            # The current radar snapshot already covers all saved favorites.
            # Do not make redundant global requests for the same data.
            self._busy_fav = False
            self.refresh_fav_btn.set_sensitive(True)
            self.fav_message.set_text(_('Updated with live radar data.'))
            return

        def work():
            checks = {}
            for favorite in favorites:
                try:
                    state, aircraft, callsign = fetch_favorite(favorite)
                    checks[favorite.key] = (state, aircraft, time.time(), callsign)
                except RateLimitError:
                    raise
                except (RuntimeError, OSError, ValueError) as exc:
                    LOG.warning(_('Favorite %s: %s'), favorite.key, exc)
                    checks[favorite.key] = ('error', None, time.time(), '')
            return checks

        self.radar._async(work, self._favorites_done)

    def _favorites_done(self, checks, error):
        if not self._alive:
            return GLib.SOURCE_REMOVE
        self._busy_fav = False
        self.refresh_fav_btn.set_sensitive(True)
        if isinstance(error, RateLimitError):
            self._cooldown_until = time.monotonic() + error.retry_after
            self.fav_message.set_text(_('API rate limit: retry after {value0}s.').format(value0=error.retry_after))
        elif error:
            self.fav_message.set_text(_('Failed to check favorites: {value0}').format(value0=error))
        else:
            # A first observation only establishes the baseline. An alert
            # requires a previously confirmed two-check absence and a later
            # plausibly airborne ADS-B measurement.
            valid_keys = {favorite.key for favorite in self.radar.favorites}
            checks = {key: value for key, value in checks.items() if key in valid_keys}
            # A global request may complete after a more recent regional
            # snapshot. Merge *before* computing transitions, so a stale
            # worldwide "offline" cannot manufacture an offline -> airborne
            # notification or overwrite a fresh local hit.
            checks.update(self._recent_live_checks())
            newly_flying = self._transitions.favorites_updated(checks)
            self._fav_status.update(checks)
            self._favorite_history.observe(checks, {fav.key: fav for fav in self.radar.favorites})
            interval = self.radar.settings['favorites_interval']
            self.fav_message.set_text(
                _('Checked at {value0} · Intervalo: {value1} min').format(value0=time.strftime('%H:%M:%S'), value1=interval // 60))
            self._render_favorites()
            self._announce_favorite_flights(newly_flying)
        return GLib.SOURCE_REMOVE

    def _refresh_emergencies(self, force=False):
        if self._busy_global or not self._alive:
            return False
        now = time.monotonic()
        if now < self._cooldown_until or now < getattr(self.radar, '_cooldown_until', 0):
            self.global_message.set_text(_('API rate limit: waiting before request.'))
            return False
        interval = self.radar.settings.get('emergencies_interval', 120)
        if now - self._last_global_request < (30 if force else interval):
            return False
        self._last_global_request = now
        self._busy_global = True
        self.refresh_em_btn.set_sensitive(False)
        self.global_message.set_text(_('Checking worldwide codes 7700, 7600 and 7500…'))
        self.radar._async(fetch_global_emergencies, self._emergencies_done)
        return True

    def _emergencies_done(self, payload, error):
        if not self._alive:
            return GLib.SOURCE_REMOVE
        self._busy_global = False
        self._station_search_busy = False
        self._station_search_request = 0
        self.refresh_em_btn.set_sensitive(True)
        if isinstance(error, RateLimitError):
            self._cooldown_until = time.monotonic() + error.retry_after
            self.global_message.set_text(_('API rate limit: retry after {value0}s.').format(value0=error.retry_after))
        elif error:
            self.global_message.set_text(_('Worldwide lookup unavailable: {value0}').format(value0=error))
        else:
            self._global_rows, self._global_errors, self._global_checked_at = payload
            self._emergency_history.observe(self._global_rows, self._global_errors,
                                            self._global_checked_at)
            new_events = self._transitions.emergencies_updated(
                self._global_rows, self._global_errors)
            if new_events and (self.radar.settings['notify_emergencies'] or
                               self.radar.settings['sound_emergencies']):
                for index, item in enumerate(new_events):
                    if not self.radar.settings['notify_emergencies']:
                        continue
                    name = item['flight'] or item['registration'] or item['hex'].upper()
                    self.radar.emit_monitor_alert(
                        _('Code {value0} · {value1}').format(value0=item['squawk'], value1=item['description']),
                        _('{value0} · transponder alert detected on the network').format(value0=name),
                        notification_id=f'emergency-{item["squawk"]}-{item["hex"]}',
                        action='app.global-alerts', sound=False)
                if self.radar.settings['sound_emergencies']:
                    # Only one alert sound per group of new events.
                    self.radar.play_monitor_alarm()
            missing = _(' · {value0} unavailable code(s)').format(value0=len(self._global_errors)) if self._global_errors else ''
            self.global_message.set_text(
                _('{value0} aircraft · {value1}').format(value0=len(self._global_rows), value1=time.strftime('%H:%M:%S', time.localtime(self._global_checked_at))) + missing)
            self._render_emergencies()
            # World-wide squawks and the regional map arrive independently.
            # Repaint markers and the visible list as soon as this result lands.
            self.radar._refresh_visible_alerts()
        # The startup burst must continue even if one provider is unavailable;
        # the favorites lookup will itself honor any shared rate-limit pause.
        self._queue_startup_favorites()
        return GLib.SOURCE_REMOVE

    def _auto_refresh(self):
        if not self._alive:
            return GLib.SOURCE_REMOVE
        if self._startup_pending:
            return GLib.SOURCE_CONTINUE
        if can_monitor_in_background(
                background_active=bool(getattr(self.radar.get_application(), '_background_active', False)),
                window_mapped=self.radar.get_mapped(), demo=self.radar.demo):
            active = self.switch.get_visible_child_name()
            # Alerts work while Visíveis is active. Proactive worldwide
            # emergencies are opt-in, to avoid hidden API traffic.
            if self.radar.favorites and (active == 'favorites' or
                                           self.radar.settings['monitor_favorites']):
                self._refresh_favorites()
            if active == 'emergencies' or self.radar.settings['monitor_emergencies']:
                self._refresh_emergencies()
        return GLib.SOURCE_CONTINUE
