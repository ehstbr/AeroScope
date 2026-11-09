"""Small independently movable GTK4 METAR card over the main map.

Only the title grip begins a drag, so the X/collapse buttons and map gestures
continue to work normally.  Positions are owned by DashboardController.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .i18n import _
from .metar_readable import describe_metar
from .sigmet_readable import describe_sigmet
from .validity_widget import sigmet_timeline
from .dashboard_drag import surface_point, dragged_position

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango, GLib


class WeatherFloatingWidget(Gtk.Box):
    def __init__(self, controller, kind, code, name, collapsed=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.controller = controller
        self.kind = kind
        self.code = code
        self.name = name
        self.collapsed = bool(collapsed)
        self.set_size_request(205 if self.collapsed else 276, -1)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.add_css_class('dashboard-weather-card')
        self.set_margin_start(14)
        self.set_margin_top(48)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        top.add_css_class('dashboard-widget-header')
        grip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        grip.set_hexpand(True)
        grip.set_cursor_from_name('grab')
        self.title_label = Gtk.Label(label=code if self.collapsed else f'{code} · {name}', xalign=0)
        title = self.title_label
        title.set_hexpand(True)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_tooltip_text(name)
        title.add_css_class('dashboard-widget-title')
        grip.append(Gtk.Image.new_from_icon_name('view-grid-symbolic'))
        grip.append(title)
        # A compact card must still identify the station; the only METAR
        # value in its collapsed header is its flight category.
        self.compact_category = Gtk.Label(label='—', xalign=1)
        self.compact_category.add_css_class('dashboard-compact-category')
        self.compact_category.set_visible(self.collapsed)
        top.append(grip)
        top.append(self.compact_category)
        self.sigmet_chip = Gtk.Label(label='⚠ SIGMET')
        self.sigmet_chip.add_css_class('dashboard-sigmet-chip')
        self.sigmet_chip.set_tooltip_text(_('SIGMET area covers this location'))
        self.sigmet_chip.set_visible(False)
        top.append(self.sigmet_chip)
        drag = Gtk.GestureDrag.new()
        drag.set_button(1)
        drag.connect('drag-begin', self._drag_begin)
        drag.connect('drag-update', self._drag_update)
        drag.connect('drag-end', self._drag_end)
        grip.add_controller(drag)

        self.collapse_button = Gtk.Button(icon_name='pan-down-symbolic' if self.collapsed
                                          else 'pan-up-symbolic')
        self.collapse_button.add_css_class('flat')
        self.collapse_button.add_css_class('dashboard-widget-button')
        self.collapse_button.set_tooltip_text(_('Expand panel') if self.collapsed else _('Collapse panel'))
        self.collapse_button.connect('clicked', self._toggle_collapsed)
        top.append(self.collapse_button)
        self.center_button = Gtk.Button(icon_name='find-location-symbolic')
        self.center_button.add_css_class('flat')
        self.center_button.add_css_class('dashboard-widget-button')
        self.center_button.set_tooltip_text(
            _('Center airport on map') if kind == 'airport'
            else _('Center weather station on map'))
        self.center_button.connect('clicked', self._center_on_map)
        top.append(self.center_button)
        close = Gtk.Button(icon_name='window-close-symbolic')
        close.add_css_class('flat')
        close.add_css_class('dashboard-widget-button')
        close.set_tooltip_text(_('Close floating panel'))
        # Removal is deferred until GTK has finished dispatching this click.
        close.connect('clicked', lambda *_args:
                      GLib.idle_add(controller.remove, kind, code))
        top.append(close)
        self.append(top)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        body.add_css_class('dashboard-widget-body')
        self.category_label = Gtk.Label(label='—', xalign=0)
        self.category_label.add_css_class('dashboard-flight-category')
        body.append(self.category_label)
        self.condition_label = Gtk.Label(xalign=0)
        self.condition_label.add_css_class('dim-label')
        self.condition_label.set_wrap(True)
        self.condition_label.set_max_width_chars(42)
        body.append(self.condition_label)
        self.data_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        body.append(self.data_box)
        self.sigmet_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.sigmet_box.add_css_class('dashboard-sigmet-box')
        self.sigmet_box.set_visible(False)
        body.append(self.sigmet_box)
        self.body = body
        self.expanded_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.expanded_content.append(body)
        self.expanded_revealer = Gtk.Revealer()
        self.expanded_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.expanded_revealer.set_transition_duration(220)
        self.expanded_revealer.set_child(self.expanded_content)
        self.expanded_revealer.set_reveal_child(not self.collapsed)
        self.append(self.expanded_revealer)

        self.observed = Gtk.Label(xalign=0)
        self.observed.add_css_class('dashboard-widget-stamp')
        self.observed.set_ellipsize(Pango.EllipsizeMode.END)
        self.expanded_content.append(self.observed)
        self.checked = Gtk.Label(xalign=0)
        self.checked.add_css_class('dashboard-widget-stamp')
        self.checked.set_ellipsize(Pango.EllipsizeMode.END)
        self.expanded_content.append(self.checked)
        self._drag_offset = None
        self._last_drag_position = None
        self._last_signature = None
        self._sigmet_signature = None
        self._flight_category = '—'
        self.update_weather(None, 'unknown')

    def _center_on_map(self, *_args):
        # Identical placement/behaviour to the aircraft card's crosshair.
        self.controller.center_location(self.kind, self.code)

    def _drag_begin(self, gesture, _x, _y):
        # GtkGestureDrag dx/dy are relative to the allocation of the widget
        # being moved. Reusing them after changing margins causes a feedback
        # loop. Anchor the pointer in the *surface* coordinate system instead.
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
        if pointer is None:
            return
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
        self.expanded_revealer.set_reveal_child(not self.collapsed)
        self.compact_category.set_visible(self.collapsed and self._flight_category != '—')
        self.title_label.set_label(self.code if self.collapsed
                                   else f'{self.code} · {self.name}')
        self.set_size_request(205 if self.collapsed else 276, -1)
        self.collapse_button.set_icon_name('pan-down-symbolic' if self.collapsed else 'pan-up-symbolic')
        self.collapse_button.set_tooltip_text(_('Expand panel') if self.collapsed else _('Collapse panel'))
        self.controller.set_collapsed(self.kind, self.code, self.collapsed)
        # The GTK revealer animates below a stationary top-left overlay anchor.
        # Never re-run normalized layout while the panel changes size.

    @staticmethod
    def _field(title, value):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        caption = Gtk.Label(label=title, xalign=0)
        caption.add_css_class('dashboard-field-title')
        row.append(caption)
        item = Gtk.Label(label=value, xalign=0)
        item.set_wrap(True)
        item.set_max_width_chars(39)
        item.add_css_class('dashboard-field-value')
        row.append(item)
        return row

    def update_weather(self, metar, state='unknown', last_check=None):
        """No reconstruction when polling the same bulletin; don't fake NOAA data."""
        category = str(getattr(metar, 'category', '') or '').upper()
        display_category = category if category in ('VFR', 'MVFR', 'IFR', 'LIFR') else '—'
        stamp = str(getattr(metar, 'observed', '') or '')
        info = describe_metar(metar) if metar is not None else None
        signature = (getattr(metar, 'raw', None), category, stamp,
                     repr(getattr(metar, 'details', None)), state)
        if signature != self._last_signature:
            self._last_signature = signature
            for old_class in ('metar-vfr', 'metar-mvfr', 'metar-ifr', 'metar-lifr'):
                self.category_label.remove_css_class(old_class)
            if display_category != '—':
                self.category_label.add_css_class('metar-' + category.lower())
            self.category_label.set_label(display_category)
            self._flight_category = display_category
            self.compact_category.set_visible(self.collapsed and display_category != '—')
            self.sigmet_chip.set_label('⚠' if display_category != '—' else '⚠ SIGMET')
            for old_class in ('metar-vfr', 'metar-mvfr', 'metar-ifr', 'metar-lifr'):
                self.compact_category.remove_css_class(old_class)
            if display_category != '—':
                self.compact_category.add_css_class('metar-' + category.lower())
            self.compact_category.set_label(display_category)
            if info is None:
                self.condition_label.set_text(_('METAR unavailable.'))
            else:
                self.condition_label.set_text(info.condition)
            while child := self.data_box.get_first_child():
                self.data_box.remove(child)
            if info is not None:
                for title, value in info.fields[:7]:
                    self.data_box.append(self._field(title, value))
            self.observed.set_text(_('Observed: {value0}').format(
                value0=stamp or _('Time not provided')))
        if state == 'error':
            self.checked.set_text(_('METAR update failed; displaying last observation.'))
        elif state in ('unknown', 'loading') and metar is None:
            self.checked.set_text(_('Checking METAR…'))
        elif state == 'missing' and metar is None:
            self.checked.set_text(_('No recent METAR available.'))
        elif last_check:
            self.checked.set_text(_('Checked: {value0} UTC').format(
                value0=datetime.fromtimestamp(last_check, timezone.utc).strftime('%d/%m/%Y %H:%M')))
        else:
            self.checked.set_text(_('Awaiting next NOAA update.'))

    def update_sigmets(self, advisories, state='loading'):
        """Independently show SIGMET hazards without changing the METAR category."""
        advisories = tuple(advisories or ())
        signature = (state, tuple((item.name, item.text, repr(item.metadata)) for item in advisories))
        if signature == self._sigmet_signature:
            return
        self._sigmet_signature = signature
        self.sigmet_chip.set_visible(bool(advisories))
        self.sigmet_chip.set_label('⚠' if self._flight_category != '—' else '⚠ SIGMET')
        while child := self.sigmet_box.get_first_child():
            self.sigmet_box.remove(child)
        self.sigmet_box.set_visible(bool(advisories) or state in ('loading', 'error'))
        if advisories:
            title = Gtk.Label(label=_('⚠ SIGMET covering this location'), xalign=0)
            title.add_css_class('dashboard-sigmet-title')
            self.sigmet_box.append(title)
            for advisory in advisories[:3]:
                decoded = describe_sigmet(advisory)
                line = Gtk.Label(label=decoded.icon + ' ' + decoded.short, xalign=0)
                line.set_wrap(True)
                line.set_max_width_chars(38)
                line.set_tooltip_text(advisory.text or decoded.description)
                self.sigmet_box.append(line)
                timeline = sigmet_timeline(advisory)
                if timeline is not None:
                    self.sigmet_box.append(timeline)
            if len(advisories) > 3:
                self.sigmet_box.append(Gtk.Label(label=_('+ {value0} more SIGMET advisories').format(
                    value0=len(advisories) - 3), xalign=0))
            footnote = Gtk.Label(label=_('Horizontal area; phenomenon may be aloft or forecast.'), xalign=0)
            footnote.set_wrap(True)
            footnote.add_css_class('dashboard-widget-stamp')
            self.sigmet_box.append(footnote)
        elif state == 'error':
            self.sigmet_box.append(Gtk.Label(label=_('SIGMET verification unavailable.'), xalign=0))
        elif state == 'loading':
            self.sigmet_box.append(Gtk.Label(label=_('Checking SIGMET…'), xalign=0))
