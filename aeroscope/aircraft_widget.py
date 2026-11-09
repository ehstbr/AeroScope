"""Movable, compact aircraft dashboard with optional photo preview button."""
from __future__ import annotations

from datetime import datetime, timezone
import time

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango

from .aircraft_card_data import snapshot
from .dashboard_drag import surface_point, dragged_position
from .i18n import _


def aircraft_age_state(plane, received_at, now=None):
    """Never report a disappeared or old ADS-B position as a live fix."""
    if received_at is None:
        return 'waiting', None
    age = max(0, (time.time() if now is None else now) - received_at)
    if plane is None or age >= 120:
        return 'stale', age
    seen = getattr(plane, 'seen', None)
    if isinstance(seen, (float, int)) and seen > 90:
        return 'stale', max(age, seen)
    return 'live', max(age, seen or 0)


class AircraftFloatingWidget(Gtk.Box):
    def __init__(self, controller, code, collapsed=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.controller = controller
        self.kind = 'aircraft'
        self.code = str(code).upper()
        self.name = self.code
        self.collapsed = bool(collapsed)
        self._drag_offset = None
        self._last_drag_position = None
        self._last_plane = None
        self._last_received_at = None
        self._present = False
        self._photo_source = None
        self._photo_texture = None
        self.set_size_request(310, -1)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.add_css_class('dashboard-weather-card')
        self.add_css_class('dashboard-aircraft-card')
        self.set_margin_start(14)
        self.set_margin_top(48)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        header.add_css_class('dashboard-widget-header')
        grip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        grip.set_hexpand(True)
        grip.set_cursor_from_name('grab')
        grip.append(Gtk.Image.new_from_icon_name('view-grid-symbolic'))
        self.title = Gtk.Label(label=self.code, xalign=0)
        self.title.set_hexpand(True)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.title.add_css_class('dashboard-widget-title')
        grip.append(self.title)
        header.append(grip)
        drag = Gtk.GestureDrag.new()
        drag.set_button(1)
        drag.connect('drag-begin', self._drag_begin)
        drag.connect('drag-update', self._drag_update)
        drag.connect('drag-end', self._drag_end)
        grip.add_controller(drag)

        self.status = Gtk.Label(label=_('Waiting for signal'), xalign=1)
        self.status.add_css_class('dashboard-aircraft-status')
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.set_max_width_chars(13)
        header.append(self.status)
        self.collapse_button = Gtk.Button(icon_name=('pan-down-symbolic' if collapsed else 'pan-up-symbolic'))
        self.collapse_button.add_css_class('flat')
        self.collapse_button.add_css_class('dashboard-widget-button')
        self.collapse_button.set_tooltip_text(_('Expand panel') if collapsed else _('Collapse panel'))
        self.collapse_button.connect('clicked', self._toggle_collapsed)
        header.append(self.collapse_button)
        # A picture button never changes the card size. The full photograph
        # stays in the existing photo preview, accessible via this tiny icon.
        self.photo_button = Gtk.Button(icon_name='image-x-generic-symbolic')
        self.photo_button.add_css_class('flat')
        self.photo_button.add_css_class('dashboard-widget-button')
        self.photo_button.set_tooltip_text(_('Enlarge photo'))
        self.photo_button.set_visible(False)
        self.photo_button.connect('clicked', self._open_photo)
        header.append(self.photo_button)
        self.center_button = Gtk.Button(icon_name='find-location-symbolic')
        self.center_button.add_css_class('flat')
        self.center_button.add_css_class('dashboard-widget-button')
        self.center_button.set_tooltip_text(_('Center aircraft on map'))
        self.center_button.connect('clicked', self._center_on_map)
        header.append(self.center_button)
        self.follow_button = Gtk.Button(icon_name='media-playback-start-symbolic')
        self.follow_button.add_css_class('flat')
        self.follow_button.add_css_class('dashboard-widget-button')
        self.follow_button.set_tooltip_text(_('Follow aircraft'))
        self.follow_button.connect('clicked', self._toggle_follow)
        header.append(self.follow_button)
        close = Gtk.Button(icon_name='window-close-symbolic')
        close.add_css_class('flat')
        close.add_css_class('dashboard-widget-button')
        close.set_tooltip_text(_('Close floating panel'))
        close.connect('clicked', lambda *_args: GLib.idle_add(controller.remove, self.kind, self.code))
        header.append(close)
        self.append(header)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.body.add_css_class('dashboard-widget-body')

        # Keep the aircraft identity in a single column. A Gtk.Picture with
        # its original texture can claim its natural width even if a smaller
        # size was requested, breaking a compact floating card. Do not embed
        # photographs in the card at all.
        identity_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.identity = Gtk.Label(label=self.code, xalign=0)
        self.identity.add_css_class('dashboard-aircraft-identity')
        self.identity.set_ellipsize(Pango.EllipsizeMode.END)
        identity_text.append(self.identity)
        self.registration = Gtk.Label(label='', xalign=0)
        self.registration.add_css_class('dashboard-aircraft-registration')
        self.registration.set_ellipsize(Pango.EllipsizeMode.END)
        identity_text.append(self.registration)
        self.model = Gtk.Label(label='', xalign=0)
        self.model.add_css_class('dashboard-aircraft-model')
        self.model.set_ellipsize(Pango.EllipsizeMode.END)
        identity_text.append(self.model)
        self.body.append(identity_text)

        # Small labeled cells are easier to scan than one long text sentence.
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        grid.add_css_class('dashboard-aircraft-grid')
        grid.set_column_homogeneous(True)
        self.metric_values = {}
        labels = (
            (0, 0, 'altitude', _('Altitude')),
            (1, 0, 'speed', _('Ground speed')),
            (0, 1, 'vertical_rate', _('Vertical speed')),
            (1, 1, 'heading', _('Ground track')),
            (0, 2, 'squawk', _('Squawk')),
            (1, 2, 'source', _('Position source')),
        )
        for col, row, key, text in labels:
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            cell.set_hexpand(True)
            caption = Gtk.Label(label=text, xalign=0)
            caption.add_css_class('dashboard-field-title')
            cell.append(caption)
            value = Gtk.Label(label='—', xalign=0)
            value.add_css_class('dashboard-aircraft-value')
            value.set_ellipsize(Pango.EllipsizeMode.END)
            cell.append(value)
            grid.attach(cell, col, row, 1, 1)
            self.metric_values[key] = value
        self.body.append(grid)

        self.alert = Gtk.Label(label='', xalign=0)
        self.alert.add_css_class('dashboard-aircraft-alert')
        self.alert.set_wrap(True)
        self.alert.set_visible(False)
        self.body.append(self.alert)

        metadata = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        metadata.add_css_class('dashboard-aircraft-metadata')
        self.position = Gtk.Label(label='—', xalign=0)
        self.position.add_css_class('dashboard-aircraft-location')
        self.position.set_ellipsize(Pango.EllipsizeMode.END)
        metadata.append(self.position)
        self.icao24 = Gtk.Label(label=self.code, xalign=0)
        self.icao24.add_css_class('dashboard-aircraft-code')
        metadata.append(self.icao24)
        self.body.append(metadata)
        # Animate vertical content with native GTK4 revealers. The header and
        # its top-left overlay anchor are never moved or re-laid out.
        self.expanded_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.expanded_content.append(self.body)
        self.expanded_revealer = Gtk.Revealer()
        self.expanded_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.expanded_revealer.set_transition_duration(220)
        self.expanded_revealer.set_child(self.expanded_content)
        self.expanded_revealer.set_reveal_child(not self.collapsed)
        self.append(self.expanded_revealer)

        # Folded card is a real mini instrument panel, not a single data line.
        # Keep the four operational values in a tiny 2x2 grid, with a concise
        # identification line and any emergency indicator. Never embed photos.
        self.compact_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.compact_body.add_css_class('dashboard-aircraft-compact-body')
        self.compact_descriptor = Gtk.Label(label='—', xalign=0)
        self.compact_descriptor.add_css_class('dashboard-aircraft-compact-descriptor')
        self.compact_descriptor.set_ellipsize(Pango.EllipsizeMode.END)
        self.compact_descriptor.set_max_width_chars(38)
        self.compact_body.append(self.compact_descriptor)
        compact_grid = Gtk.Grid(column_spacing=10, row_spacing=4)
        compact_grid.set_column_homogeneous(True)
        compact_grid.add_css_class('dashboard-aircraft-compact-grid')
        self.compact_values = {}
        for col, row, key, title in (
                (0, 0, 'altitude', _('Altitude')),
                (1, 0, 'speed', _('Ground speed')),
                (0, 1, 'heading', _('Ground track')),
                (1, 1, 'vertical_rate', _('Vertical speed'))):
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            caption = Gtk.Label(label=title, xalign=0)
            caption.add_css_class('dashboard-aircraft-compact-caption')
            cell.append(caption)
            value = Gtk.Label(label='—', xalign=0)
            value.add_css_class('dashboard-aircraft-compact-value')
            value.set_ellipsize(Pango.EllipsizeMode.END)
            cell.append(value)
            compact_grid.attach(cell, col, row, 1, 1)
            self.compact_values[key] = value
        self.compact_body.append(compact_grid)
        self.compact_alert = Gtk.Label(label='', xalign=0)
        self.compact_alert.add_css_class('dashboard-aircraft-alert')
        self.compact_alert.set_ellipsize(Pango.EllipsizeMode.END)
        self.compact_alert.set_visible(False)
        self.compact_body.append(self.compact_alert)
        self.compact_revealer = Gtk.Revealer()
        self.compact_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.compact_revealer.set_transition_duration(220)
        self.compact_revealer.set_child(self.compact_body)
        self.compact_revealer.set_reveal_child(self.collapsed)
        self.append(self.compact_revealer)
        self.updated = Gtk.Label(label=_('Awaiting aircraft position.'), xalign=0)
        self.updated.add_css_class('dashboard-widget-stamp')
        self.expanded_content.append(self.updated)
        self._refresh_status()
        self.update_actions()

    def update_actions(self):
        """Reflect the current global follow state, including sidebar changes."""
        live_position = bool(self._present and self._last_plane is not None)
        self.center_button.set_sensitive(live_position)
        self.follow_button.set_sensitive(live_position)
        following = (self.controller.radar.follow and
                     self.controller.radar.selected_hex == self.code.lower())
        self.follow_button.set_icon_name('media-playback-pause-symbolic'
                                         if following else 'media-playback-start-symbolic')
        self.follow_button.set_tooltip_text(_('Stop following') if following
                                            else _('Follow aircraft'))
        if following:
            self.follow_button.add_css_class('dashboard-follow-active')
        else:
            self.follow_button.remove_css_class('dashboard-follow-active')

    def _center_on_map(self, *_args):
        self.controller.center_aircraft(self.code)

    def _toggle_follow(self, *_args):
        self.controller.toggle_aircraft_follow(self.code)

    def _drag_begin(self, gesture, _x, _y):
        pointer = surface_point(gesture)
        if pointer is None:
            self._drag_offset = None
            return
        x, y = self.controller.current_pixels(self)
        self._drag_offset = (x, y, *pointer)
        self._last_drag_position = (x, y)

    def _drag_update(self, gesture, _dx, _dy):
        if self._drag_offset is None:
            return
        pointer = surface_point(gesture)
        if pointer is not None:
            self._last_drag_position = dragged_position(self._drag_offset, pointer)
            self.controller.move_pixels(self, *self._last_drag_position, persist=False)

    def _drag_end(self, gesture, _dx, _dy):
        if self._drag_offset is None:
            return
        pointer = surface_point(gesture)
        if pointer is not None:
            self._last_drag_position = dragged_position(self._drag_offset, pointer)
        if self._last_drag_position is not None:
            self.controller.move_pixels(self, *self._last_drag_position, persist=True)
        self._drag_offset = None
        self._last_drag_position = None

    def _toggle_collapsed(self, *_args):
        self.collapsed = not self.collapsed
        self.compact_alert.set_visible(self.collapsed and bool(self.compact_alert.get_text()))
        self.expanded_revealer.set_reveal_child(not self.collapsed)
        self.compact_revealer.set_reveal_child(self.collapsed)
        self.collapse_button.set_icon_name('pan-down-symbolic' if self.collapsed else 'pan-up-symbolic')
        self.collapse_button.set_tooltip_text(_('Expand panel') if self.collapsed else _('Collapse panel'))
        self.controller.set_collapsed(self.kind, self.code, self.collapsed)
        # Do NOT call relayout here. The card's dimensions change during the
        # ~220ms animation, but Gtk.Overlay's START margins stay unchanged.

    def update_plane(self, plane):
        """Preserve the last FIX but mark it unavailable when outside radar."""
        self._present = plane is not None
        if plane is not None:
            self._last_plane = plane
            self._last_received_at = time.time() - max(0, float(plane.seen or 0))
            # The UI updates only the values, never rebuilds widget rows while
            # polling. This also keeps dragging stable during ADS-B refreshes.
            fact = snapshot(plane, self.controller.radar.settings.get('speed', 'kmh'))
            self.name = plane.registration or plane.flight or self.code
            self.title.set_text(self.name)
            self.title.set_tooltip_text(self.code)
            self.identity.set_text(fact['flight'])
            self.registration.set_text(fact['registration'])
            self.model.set_text(fact['model'])
            self.model.set_tooltip_text(fact['model'])
            for key, label in self.metric_values.items():
                label.set_text(fact[key])
            self.position.set_text(_('Position: {value0}').format(value0=fact['position']))
            self.icao24.set_text(_('ICAO24: {value0}').format(value0=fact['icao24']))
            descriptor = ' · '.join(part for part in (
                fact['flight'] if fact['flight'] != self.name else '',
                fact['model'] if fact['model'] != _('Unknown') else '',
            ) if part)
            self.compact_descriptor.set_text(descriptor or fact['icao24'])
            for key, label in self.compact_values.items():
                label.set_text(fact[key])
            self.compact_alert.set_text(fact['alert'])
            self.compact_alert.set_visible(self.collapsed and bool(fact['alert']))
            self.compact_alert.remove_css_class('dashboard-alert-critical')
            self.compact_alert.remove_css_class('dashboard-alert-warning')
            if fact['alert_level'] == 'critical':
                self.compact_alert.add_css_class('dashboard-alert-critical')
            elif fact['alert_level'] == 'warning':
                self.compact_alert.add_css_class('dashboard-alert-warning')
            self.alert.set_text(fact['alert'])
            self.alert.set_visible(bool(fact['alert']))
            self.alert.remove_css_class('dashboard-alert-critical')
            self.alert.remove_css_class('dashboard-alert-warning')
            if fact['alert_level'] == 'critical':
                self.alert.add_css_class('dashboard-alert-critical')
            elif fact['alert_level'] == 'warning':
                self.alert.add_css_class('dashboard-alert-warning')
        self._refresh_status()
        self.update_actions()

    def _refresh_status(self, now=None):
        state, age = aircraft_age_state(self._last_plane if self._present else None,
                                        self._last_received_at, now)
        self.status.remove_css_class('dashboard-aircraft-live')
        self.status.remove_css_class('dashboard-aircraft-stale')
        if state == 'live':
            self.status.set_text(_('Live'))
            self.status.add_css_class('dashboard-aircraft-live')
        elif state == 'stale':
            self.status.set_text(_('Signal lost'))
            self.status.add_css_class('dashboard-aircraft-stale')
        else:
            self.status.set_text(_('Waiting for signal'))
        if self._last_received_at is not None:
            moment = datetime.fromtimestamp(self._last_received_at, timezone.utc).strftime('%d/%m %H:%M')
            self.updated.set_text(_('Last ADS-B position: {value0} UTC').format(value0=moment))
        else:
            self.updated.set_text(_('Awaiting aircraft position.'))

    def update_photo(self, photo, enabled=True):
        """Only enable a compact preview action; never embed an image."""
        if not enabled or not isinstance(photo, dict) or not photo.get('image'):
            self.photo_button.set_visible(False)
            return
        if self._photo_source is photo and self._photo_texture is not None:
            self.photo_button.set_visible(True)
            return
        try:
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(photo['image']))
        except (ValueError, TypeError, GLib.Error):
            self.photo_button.set_visible(False)
            return
        self._photo_source = photo
        self._photo_texture = texture
        credit = str(photo.get('photographer') or _('Unknown author'))
        self.photo_button.set_tooltip_text(
            _('Enlarge photo') + ' · © ' + credit + ' / Planespotters.net')
        self.photo_button.set_visible(True)

    def _open_photo(self, *_args):
        photo = self._photo_source
        if photo and self._photo_texture is not None:
            reg = self._last_plane.registration if self._last_plane else ''
            self.controller.radar._show_photo_preview(self.code.lower(), photo,
                                                        self._photo_texture, reg)
