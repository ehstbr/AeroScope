"""Floating METAR dashboard anchored to the *screen*, not geographic points."""
from __future__ import annotations

import logging
import time

from .dashboard_layout import (MAX_WIDGETS, load_layout, save_layout,
                               widget_key, bounded_fraction, anchor_fraction, anchor_pixel)
from .floating_widget import WeatherFloatingWidget
from .dashboard_fade import fade_widget
from .aircraft_widget import AircraftFloatingWidget
from .i18n import _
from .data import AIRPORTS

from gi.repository import GLib, Gtk


class DashboardController:
    def __init__(self, radar, overlay):
        self.radar = radar
        self.overlay = overlay
        self.layout = load_layout()
        self.cards = {}
        self._last_size = None
        self._restore_cards()
        GLib.timeout_add_seconds(3, self._watch_size)
        GLib.timeout_add_seconds(5, self.update_aircraft_clocks)

    @property
    def restore_fullscreen(self):
        return bool(self.layout['fullscreen'])

    def _watch_size(self):
        dimensions = (self.overlay.get_width(), self.overlay.get_height())
        if dimensions != self._last_size and all(size > 0 for size in dimensions):
            self._last_size = dimensions
            self.relayout()
        return GLib.SOURCE_CONTINUE

    def _restore_cards(self):
        for entry in self.layout['widgets']:
            self._create(entry)
        self.relayout()

    def _create(self, entry, *, animate=False):
        key = widget_key(entry['kind'], entry['code'])
        if key in self.cards:
            return self.cards[key]
        kind, code = entry['kind'], entry['code']
        name = (AIRPORTS[code][1] if kind == 'airport' and code in AIRPORTS
                else _('Weather station') if kind == 'station' else _('Airport'))
        if kind == 'aircraft':
            card = AircraftFloatingWidget(self, code, collapsed=entry['collapsed'])
        else:
            card = WeatherFloatingWidget(self, kind, code, name,
                                         collapsed=entry['collapsed'])
        self.overlay.add_overlay(card)
        self.overlay.set_measure_overlay(card, False)
        self.cards[key] = card
        if animate:
            fade_widget(card, appearing=True, enabled=self._animations_enabled())
        if kind == 'aircraft':
            self.refresh_aircraft_card(card)
        else:
            self.refresh_card(card)
        return card

    def has(self, kind, code):
        return widget_key(kind, code) in self.cards

    def add(self, kind, code, position=None):
        try:
            key = widget_key(kind, code)
        except ValueError:
            return False
        if key in self.cards:
            return False
        code = str(code).strip().upper()  # Match layout normalization and card.code
        if len(self.cards) >= MAX_WIDGETS:
            self.radar.notify(_('Maximum of {value0} floating panels reached.').format(value0=MAX_WIDGETS))
            return False
        if kind == 'airport' and code not in AIRPORTS:
            return False
        if kind == 'aircraft' and code.lower() not in self.radar.records:
            return False
        # Stagger cards so a second one doesn't cover the first completely.
        index = len(self.cards)
        entry = {'kind': kind, 'code': code, 'x': min(0.8, 0.03 + index * 0.09),
                 'y': min(0.7, 0.12 + index * 0.09), 'collapsed': False}
        if kind == 'station' and position is not None:
            from .station_favorites import valid_position
            try:
                entry['lat'], entry['lon'] = valid_position(*position)
            except (ValueError, TypeError, OverflowError):
                pass
        self.layout['widgets'].append(entry)
        self._create(entry, animate=True)
        self.relayout()
        self._persist()
        if kind != 'aircraft':
            self.radar.weather.favorites_changed()
        else:
            self.request_aircraft_photo(code.lower())
        return True

    @staticmethod
    def _animations_enabled():
        settings = Gtk.Settings.get_default()
        return settings is None or bool(settings.get_property('gtk-enable-animations'))

    def remove(self, kind, code):
        """Persist the closure immediately; unparent after its short fade-out.

        The card leaves the live registry at once, so duplicate clicks and
        periodic data/position updates cannot interfere with its animation.
        """
        key = widget_key(kind, code)
        card = self.cards.pop(key, None)
        if card is None:
            return
        self.layout['widgets'] = [entry for entry in self.layout['widgets']
                                  if widget_key(entry['kind'], entry['code']) != key]
        self._persist()
        if kind != 'aircraft':
            self.radar.weather.favorites_changed()

        # Avoid further clicks/drags on the disappearing card.
        card.set_can_target(False)
        # Unparent on GTK's idle cycle, never from a frame-clock callback.
        fade_widget(card, appearing=False, enabled=self._animations_enabled(),
                    on_finished=lambda: GLib.idle_add(self._finish_card_removal, card))

    def _finish_card_removal(self, card):
        if card.get_parent() is self.overlay:
            self.overlay.remove_overlay(card)
        return GLib.SOURCE_REMOVE

    def set_fullscreen_saved(self, fullscreen):
        self.layout['fullscreen'] = bool(fullscreen)
        self._persist()

    def _persist(self):
        try:
            save_layout(self.layout)
        except (OSError, ValueError, TypeError) as exc:
            logging.getLogger('aeroscope.dashboard').warning(
                'Dashboard layout could not be saved: %s', exc)

    def _entry(self, card):
        for entry in self.layout['widgets']:
            if entry['kind'] == card.kind and entry['code'] == card.code:
                return entry
        return None

    def set_collapsed(self, kind, code, collapsed):
        card = self.cards.get(widget_key(kind, code))
        if card is not None:
            entry = self._entry(card)
            if entry is not None:
                entry['collapsed'] = bool(collapsed)
                self._persist()

    def _available(self, card):
        width = max(0, self.overlay.get_width() - max(276, card.get_width()))
        height = max(0, self.overlay.get_height() - max(95, card.get_height()))
        return width, height

    def current_pixels(self, card):
        return float(card.get_margin_start()), float(card.get_margin_top())

    def move_pixels(self, card, x, y, *, persist=False):
        entry = self._entry(card)
        if entry is None:
            return
        available_x, available_y = self._available(card)
        # A narrowed screen never leaves the X button beyond the visible edge.
        x = max(0, min(available_x, x))
        y = max(0, min(available_y, y))
        card.set_margin_start(int(x))
        card.set_margin_top(int(y))
        entry['x'] = bounded_fraction(x / available_x if available_x else 0, 0)
        entry['y'] = bounded_fraction(y / available_y if available_y else 0, 0)
        # Anchors use the complete viewport; changing card height must not
        # influence the position of its top-left corner.
        entry['anchor_x'] = anchor_fraction(x, self.overlay.get_width())
        entry['anchor_y'] = anchor_fraction(y, self.overlay.get_height())
        if persist:
            self._persist()

    def relayout(self):
        """Position cards by stable top-left anchors, regardless of card size.

        Legacy 0.3.62 layouts used the remaining space (viewport minus card)
        for x/y. Convert once on first render, preserving the visible position
        rather than interpreting those fractions as full-viewport fractions.
        """
        width, height = self.overlay.get_width(), self.overlay.get_height()
        if width <= 0 or height <= 0:
            return GLib.SOURCE_REMOVE
        migrated = False
        for card in self.cards.values():
            entry = self._entry(card)
            if entry is None or card._drag_offset is not None:
                continue
            max_x, max_y = self._available(card)
            if 'anchor_x' not in entry or 'anchor_y' not in entry:
                # Old saved positions are in fractions of *available* space.
                old_x = round(entry['x'] * max_x)
                old_y = round(entry['y'] * max_y)
                entry['anchor_x'] = anchor_fraction(old_x, width)
                entry['anchor_y'] = anchor_fraction(old_y, height)
                migrated = True
            card.set_margin_start(anchor_pixel(entry['anchor_x'], width, max_x))
            card.set_margin_top(anchor_pixel(entry['anchor_y'], height, max_y))
        if migrated:
            self._persist()
        return GLib.SOURCE_REMOVE

    def station_codes(self):
        return {
            AIRPORTS[card.code][0] if card.kind == 'airport' else card.code
            for card in self.cards.values()
            if card.kind == 'station' or (card.kind == 'airport' and card.code in AIRPORTS)
        }

    def _station_for_card(self, card):
        return AIRPORTS[card.code][0] if card.kind == 'airport' else card.code

    def _card_position(self, card, metar=None):
        if card.kind == 'airport':
            return AIRPORTS[card.code][2:4] if card.code in AIRPORTS else None
        entry = self._entry(card)
        if entry is not None and 'lat' in entry and 'lon' in entry:
            return (entry['lat'], entry['lon'])
        if card.code in self.radar.favorite_stations:
            return self.radar.favorite_stations[card.code]
        if metar is not None:
            return (metar.lat, metar.lon)
        return None

    def refresh_card(self, card):
        if card.kind == 'aircraft':
            self.refresh_aircraft_card(card)
            return
        weather = getattr(self.radar, 'weather', None)
        if weather is None:
            return
        code = self._station_for_card(card)
        state, metar, _error = weather.favorite_metar_status(code)
        cache = weather._airport_metars.get(code)
        last_check = (time.time() - (time.monotonic() - cache[0])) if cache else None
        card.update_weather(metar, state, last_check)
        position = self._card_position(card, metar)
        if position is not None:
            sigmet_state, advisories = weather.sigmet_coverage(*position)
        else:
            sigmet_state, advisories = 'invalid', ()
        card.update_sigmets(advisories, sigmet_state)

    def update_weather(self):
        for card in tuple(self.cards.values()):
            if card.kind != 'aircraft':
                self.refresh_card(card)

    def refresh_aircraft_card(self, card):
        if card.kind != 'aircraft':
            return
        plane = self.radar.records.get(card.code.lower())
        card.update_plane(plane)
        self.update_aircraft_photo(card.code.lower())
        if plane is not None:
            self.request_aircraft_photo(card.code.lower())

    def center_location(self, kind, code):
        """Navigate from a weather card, including non-favorite NOAA stations."""
        if kind == 'airport':
            if code not in AIRPORTS:
                return False
            self.radar._center_airport(code)
            return True
        if kind != 'station':
            return False
        card = self.cards.get(widget_key(kind, code))
        if card is None:
            return False
        weather = getattr(self.radar, 'weather', None)
        metar = weather.cached_metar(code) if weather is not None else None
        position = self._card_position(card, metar)
        if position is None:
            return False
        return self.radar._center_station(code, position=position)

    def center_aircraft(self, code):
        hexid = str(code).lower()
        if hexid not in self.radar.records:
            return False
        self.radar._center_aircraft_from_menu(hexid)
        self.update_aircraft_actions()
        return True

    def toggle_aircraft_follow(self, code):
        hexid = str(code).lower()
        if hexid not in self.radar.records:
            return False
        if self.radar.selected_hex == hexid and self.radar.follow:
            self.radar.follow = False
        else:
            self.radar.select_plane(hexid)
            self.radar.follow = True
        self.radar._render_details()  # Sync the existing sidebar Follow control.
        self.update_aircraft_actions()
        return True

    def update_aircraft_actions(self):
        for card in tuple(self.cards.values()):
            if card.kind == 'aircraft':
                card.update_actions()

    def update_aircraft(self):
        for card in tuple(self.cards.values()):
            if card.kind == 'aircraft':
                self.refresh_aircraft_card(card)

    def update_aircraft_clocks(self):
        for card in tuple(self.cards.values()):
            if card.kind == 'aircraft':
                card._refresh_status()
                card.update_actions()
        return GLib.SOURCE_CONTINUE

    def update_aircraft_photo(self, hexid):
        card = self.cards.get(widget_key('aircraft', hexid))
        if card is not None:
            photo = self.radar.photo_info.get(hexid)
            card.update_photo(photo, enabled=bool(self.radar.settings.get('photos')))

    def request_aircraft_photo(self, hexid):
        """Reuse the existing Planespotters fetch/pending set, not a new API call."""
        if not self.radar.settings.get('photos') or self.radar.demo:
            return
        if (hexid in self.radar.photo_info or hexid in self.radar.photo_errors
                or hexid in self.radar.photo_pending):
            return
        plane = self.radar.records.get(hexid)
        if plane is None:
            return
        self.radar.photo_pending.add(hexid)
        self.radar._async(lambda: self.radar._fetch_photo(hexid, plane.registration),
                          lambda photo, error: self.radar._photo_done(hexid, photo, error))

