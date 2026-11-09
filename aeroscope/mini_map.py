"""Compact detached live map for AeroScope; shares main radar data and tiles.

Double-click an aircraft to return to the main window. A right click opens
context actions; single click selects without closing PiP. The keep-above
option uses an X11 EWMH request only; Wayland compositors control stacking.
"""
from __future__ import annotations
from .i18n import _

import logging
import math
import time

from gi.repository import Adw, Gtk, Gdk, GLib, Shumate

from .pip_scale import compact_scale
from .tower_radar import meters_per_pixel
from .pip_windowing import request_window_above, request_window_corner

LOG = logging.getLogger('aeroscope.pip')


class MiniMapWindow(Adw.ApplicationWindow):
    def __init__(self, application, radar):
        super().__init__(application=application, title=_('AeroScope · Mini-map'),
                         default_width=450, default_height=290)
        self.radar = radar
        # The PiP is another viewport on the same radar, not a different
        # presentation. All appearance flags belong to the primary settings.
        self.settings = radar.settings
        self._markers = {}
        self._airport_view_key = None
        self._syncing_view = False
        self._view_timer = 0
        self._camera_generation = 0
        self._above_status = 'not-ready'
        self._placement_monitor = None
        self._placement_serial = 0
        self._placement_attempts = 0
        self._always_top = bool(radar.settings.get('pip_always_on_top', True))
        self.add_css_class('minimap-window')
        self.set_resizable(True)  # Edges resize; no redundant maximize/minimize buttons.
        self.connect('close-request', self._on_close)
        self.connect('map', self._on_mapped)

        toolbar = Adw.ToolbarView()
        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        self.toast.set_child(toolbar)
        # A GTK WindowHandle provides draggable Wayland-compatible decoration
        # without the large platform minimums of Gtk.HeaderBar.
        self.pip_window_handle = (Gtk.WindowHandle() if hasattr(Gtk, 'WindowHandle')
                                  else Gtk.Box(orientation=Gtk.Orientation.VERTICAL))
        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        strip.add_css_class('pip-compact-strip')
        if hasattr(self.pip_window_handle, 'set_child'):
            self.pip_window_handle.set_child(strip)
        else:
            self.pip_window_handle.append(strip)  # older GTK4, no drag handle
        menu = Gtk.MenuButton(icon_name='open-menu-symbolic')
        menu.add_css_class('flat')
        menu.add_css_class('minimap-top-control')
        menu.set_tooltip_text(_('Mini-map options'))
        strip.append(menu)
        title = Gtk.Label(label='AeroScope', xalign=.5)
        title.set_hexpand(True)
        title.add_css_class('minimap-title')
        strip.append(title)
        back = Gtk.Button(icon_name='view-fullscreen-symbolic')
        back.add_css_class('flat')
        back.add_css_class('minimap-top-control')
        back.set_tooltip_text(_('Open main window'))
        back.connect('clicked', lambda *_: application.show_main_window())
        strip.append(back)
        close = Gtk.Button(icon_name='window-close-symbolic')
        close.add_css_class('flat')
        close.add_css_class('minimap-top-control')
        close.set_tooltip_text(_('Hide mini-map'))
        close.connect('clicked', lambda *_: self.hide())
        strip.append(close)
        popup = Gtk.Popover()
        popup_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        popup_content.set_margin_start(10)
        popup_content.set_margin_end(10)
        popup_content.set_margin_top(8)
        popup_content.set_margin_bottom(8)
        restore = Gtk.Button(label=_('Open main window'))
        restore.add_css_class('flat')
        restore.connect('clicked', lambda *_: (popup.popdown(), application.show_main_window()))
        popup_content.append(restore)
        self.above_check = Gtk.CheckButton(label=_('Always on top'))
        self.above_check.set_active(self._always_top)
        self.above_check.connect('toggled', self._top_toggled)
        self.above_check.set_visible(False)  # only shown after verified X11 request
        popup_content.append(self.above_check)
        self.above_help = Gtk.Button(label=_('How to enable always-on-top'))
        self.above_help.add_css_class('flat')
        self.above_help.connect('clicked', lambda *_: (popup.popdown(), self._show_above_help()))
        popup_content.append(self.above_help)
        self.above_hint = Gtk.Label(label=_('Window stacking is controlled by the desktop environment.'),
                                    xalign=0, wrap=True, max_width_chars=36)
        self.above_hint.add_css_class('dim-label')
        self.above_hint.add_css_class('minimap-explanation')
        popup_content.append(self.above_hint)
        popup.set_child(popup_content)
        menu.set_popover(popup)
        toolbar.add_top_bar(self.pip_window_handle)

        self.simple_map = Shumate.SimpleMap.new()
        self.simple_map.set_show_zoom_buttons(False)
        self.simple_map.set_map_source(radar.map_sources[radar.settings['map']])
        # Original scale shows two units and overlaps attribution at tiny sizes.
        if self.simple_map.get_scale() is not None:
            self.simple_map.get_scale().set_visible(False)
        attribution = self.simple_map.get_license()
        if attribution is not None:
            attribution.add_css_class('minimap-license')

        self.map = self.simple_map.get_map()
        if hasattr(self.map, 'set_animate_zoom'):
            self.map.set_animate_zoom(True)
        self.viewport = self.simple_map.get_viewport()
        from .map_orientation import lock_north_up
        lock_north_up(self.viewport, self.map, Gtk)
        self.marker_layer = Shumate.MarkerLayer.new(self.viewport)
        self.simple_map.add_overlay_layer(self.marker_layer)
        overlay = Gtk.Overlay()
        overlay.set_child(self.simple_map)
        # Share the *exact* main-map Cairo rendering implementation for
        # control-tower shading, distance rings, the sweeping beam and the
        # optional aircraft-relative clock.  Only viewport coordinates differ.
        self.radar_decoration = Gtk.DrawingArea()
        self.radar_decoration.set_can_target(False)
        self.radar_decoration.set_draw_func(self._draw_radar)
        self.radar_decoration.set_visible(bool(self.settings['tower']))
        overlay.add_overlay(self.radar_decoration)
        self.clock_decoration = Gtk.DrawingArea()
        self.clock_decoration.set_can_target(False)
        self.clock_decoration.set_draw_func(self._draw_clock_overlay)
        self.clock_decoration.set_visible(bool(self.settings['clock_ring']))
        overlay.add_overlay(self.clock_decoration)
        # Weather annotations use the same NOAA manager and presentation flags.
        self.weather_view = self.radar.weather.attach(self.simple_map, overlay, self.marker_layer)
        # The original PiP omitted the main map's airport markers entirely.
        self.airport_layer = Shumate.MarkerLayer.new(self.viewport)
        if hasattr(self.simple_map, 'insert_overlay_layer_behind'):
            self.simple_map.insert_overlay_layer_behind(self.airport_layer, self.marker_layer)
        else:
            self.simple_map.add_overlay_layer(self.airport_layer)

        zooms = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        zooms.set_halign(Gtk.Align.END)
        zooms.set_valign(Gtk.Align.START)
        zooms.set_margin_end(5)
        zooms.set_margin_top(5)
        zooms.add_css_class('minimap-zoom-group')
        for symbol, delta, tooltip in (('list-add-symbolic', 1, _('Zoom in')),
                                       ('list-remove-symbolic', -1, _('Zoom out'))):
            button = Gtk.Button(icon_name=symbol)
            button.add_css_class('minimap-zoom-button')
            button.set_tooltip_text(tooltip)
            button.connect('clicked', self._zoom_clicked, delta)
            zooms.append(button)
        geo = Gtk.Button(icon_name='find-location-symbolic')
        geo.add_css_class('minimap-zoom-button')
        geo.set_tooltip_text(_('Center using system geolocation'))
        geo.connect('clicked', lambda *_: self.radar.locate())
        zooms.append(geo)
        overlay.add_overlay(zooms)

        self.compact_scale = Gtk.DrawingArea()
        self.compact_scale.set_content_width(104)
        self.compact_scale.set_content_height(27)
        self.compact_scale.set_halign(Gtk.Align.START)
        self.compact_scale.set_valign(Gtk.Align.END)
        self.compact_scale.set_margin_start(5)
        self.compact_scale.set_margin_bottom(6)
        self.compact_scale.set_draw_func(self._draw_compact_scale)
        overlay.add_overlay(self.compact_scale)
        toolbar.set_content(overlay)
        self.sync_initial_view()
        for name in ('latitude', 'longitude', 'zoom-level'):
            self.viewport.connect(f'notify::{name}', self._view_changed)

    def _tower_sweep_enabled(self):
        """The mini-map uses the primary radar's scan state and timing."""
        return self.radar._tower_sweep_enabled()

    def _tower_sweep_angle(self, now=None):
        return self.radar._tower_sweep_angle(now)

    def _tower_ring_distance_nm(self, _cx, _cy, pixel_radius):
        return (pixel_radius * meters_per_pixel(self.viewport.get_latitude(),
                                               self.viewport.get_zoom_level()) / 1852.0)

    def _selected_tower_reference(self, width, height):
        """Project the actual selected *visible* fix into the mini viewport."""
        selected = self._markers.get(self.radar.selected_hex)
        if selected is None:
            return None
        try:
            x, y = self.viewport.location_to_widget_coords(
                self.map, selected.marker.get_latitude(), selected.marker.get_longitude())
            heading = float(selected.bearing)
            if not all(map(math.isfinite, (x, y, heading))):
                return None
            if not (0 <= x <= width and 0 <= y <= height):
                return None
            return x, y, heading % 360
        except (ValueError, AttributeError, TypeError):
            return None

    def _draw_radar(self, area, cr, width, height):
        # Reuse the exact source of the main window's tower decoration, so
        # rings, labels, sweep gradient and palette cannot diverge over time.
        from .ui import RadarWindow
        RadarWindow._draw_radar(self, area, cr, width, height)

    def _draw_clock_overlay(self, _area, cr, width, height):
        if self.settings['clock_ring'] and self.radar.selected_hex is not None:
            from .ui import RadarWindow
            RadarWindow._draw_relative_clock(self, cr, width, height)

    def redraw_tower_sweep(self):
        """Called on the primary 50 ms scan tick; never starts a second scan."""
        if self.get_visible() and self.settings['tower']:
            self.radar_decoration.queue_draw()

    def sync_visuals(self):
        """Apply the current map appearance without fetching any new data."""
        source = self.radar.map_sources[self.settings['map']]
        if self.simple_map.get_map_source() is not source:
            self.simple_map.set_map_source(source)
        self.radar_decoration.set_visible(bool(self.settings['tower']))
        self.clock_decoration.set_visible(bool(self.settings['clock_ring']))
        self.radar_decoration.queue_draw()
        self.clock_decoration.queue_draw()
        self.compact_scale.queue_draw()
        # The NOAA layers share the radar settings; force their Cairo redraw
        # for a different base-map tile size or tower-mode contrast.
        self.weather_view.sigmet_canvas.queue_draw()
        self._airport_view_key = None
        if self.get_visible():
            self.sync_airports()

    def sync_airports(self):
        """Use the same cached-airport/METAR styling as the main viewport.

        This is display-only: no additional NOAA or ADS-B requests. Rebuild
        only when a visible preference, viewport or cached METAR changes.
        """
        if not self.get_visible():
            return
        from .data import AIRPORTS
        from .airport_weather_badge import airport_metar_tooltip, metar_badge
        enabled = bool(self.settings['weather_metar'])
        checked = []
        for iata, (icao, name, lat, lon) in AIRPORTS.items():
            try:
                x, y = self.viewport.location_to_widget_coords(self.map, lat, lon)
                if not (math.isfinite(x) and math.isfinite(y) and
                        -80 <= x <= self.map.get_width()+80 and
                        -80 <= y <= self.map.get_height()+80):
                    continue
            except (AttributeError, TypeError, ValueError):
                continue
            report = self.radar.weather.cached_metar(icao) if enabled else None
            category = metar_badge(report) if report else None
            checked.append((iata, icao, name, lat, lon, report, category))
        key = (bool(self.settings['show_airports']), enabled,
               bool(self.settings['enable_hover']),
               frozenset(self.radar.favorite_airports),
               tuple((v[0], v[6]) for v in checked))
        if key == self._airport_view_key:
            self.sync_airport_selection()
            return
        self._airport_view_key = key
        self.airport_layer.remove_all()
        self._airport_buttons = {}
        if not self.settings['show_airports']:
            return
        for iata, icao, name, lat, lon, report, category in checked:
            mark = Shumate.Marker.new()
            mark.set_location(lat, lon)
            tooltip = airport_metar_tooltip(name, iata, icao, report, enabled=enabled)
            button = self.radar._create_airport_marker_button(
                iata, tooltip, lambda _button, code=iata: self._select_airport(code),
                on_context=lambda widget, x, y, code=iata:
                    self.radar.show_airport_context_menu(code, widget, x, y))
            if iata in self.radar.favorite_airports:
                star = Gtk.Label(label='★')
                star.add_css_class('airport-favorite-star')
                button.get_child().append(star)
            if category:
                button.add_css_class('airport-weather-active')
                button.add_css_class('metar-' + category.lower())
                badge = Gtk.Label(label=category)
                badge.add_css_class('airport-weather-category')
                button.get_child().append(badge)
            mark.set_child(button)
            self.airport_layer.add_marker(mark)
            self._airport_buttons[iata] = button

    def sync_airport_selection(self):
        for code, button in getattr(self, '_airport_buttons', {}).items():
            if code == self.radar.selected_airport:
                button.add_css_class('selected-location')
            else:
                button.remove_css_class('selected-location')

    def _select_airport(self, code):
        self.radar._center_airport(code)
        self.get_application().show_main_window()

    def notify(self, message):
        """Present geolocation and other short notices in the visible PiP."""
        self.toast.add_toast(Adw.Toast.new(str(message)))

    def set_source_monitor(self, monitor):
        """Remember which screen contained the main window before it hid.

        Only ask for a new position when opening the PiP. Later resizing,
        dragging or zooming must not keep snapping it back to the corner.
        """
        self._placement_monitor = monitor
        self._placement_serial += 1
        self._placement_attempts = 0
        if self.get_mapped():
            GLib.timeout_add(100, self._place_after_present,
                             self._placement_serial)

    def _place_after_present(self, serial):
        if serial != self._placement_serial or not self.get_mapped():
            return GLib.SOURCE_REMOVE
        result = request_window_corner(self, self._placement_monitor, margin=24)
        if result == 'not-ready' and self._placement_attempts < 5:
            self._placement_attempts += 1
            GLib.timeout_add(150, self._place_after_present, serial)
        elif result == 'unavailable':
            LOG.debug(_('Automatic PiP placement unavailable on this display backend.'))
        return GLib.SOURCE_REMOVE

    def _on_mapped(self, *_):
        GLib.idle_add(self._apply_always_top)
        GLib.idle_add(self.sync_airports)
        if self._placement_monitor is not None:
            GLib.timeout_add(100, self._place_after_present,
                             self._placement_serial)

    def _apply_always_top(self):
        self._above_status = request_window_above(self, self._always_top)
        can_toggle = self._above_status == 'requested'
        # On X11, show only the working native checkbox. On Wayland, show only
        # the manual instructions. No fake application-level authorization.
        self.above_check.set_visible(can_toggle)
        self.above_help.set_visible(not can_toggle)
        self.above_hint.set_text(
            _('Request sent to X11 window manager (may be ignored).')
            if can_toggle else
            'Wayland: GNOME/KDE controlam quais janelas ficam acima.')
        return GLib.SOURCE_REMOVE

    def _show_above_help(self):
        explanation = (
            _('On Wayland, applications cannot request a universal permission to stay above other windows. Use your desktop environment instead.\n\nGNOME: select the mini-map, press Alt+Space or right-click the title bar. If the menu offers “Always on Top” or “Always Above”, enable it. If the option is unavailable in your GNOME version, you may need a compatible GNOME Shell extension.\n\nKDE Plasma: select the mini-map and press Alt+F3 → More Actions → Keep Above Others. To make it permanent, select Configure Special Window Settings and enable “Keep Above”.\n\nOptions and labels may vary by desktop version.'))
        dialog = Adw.MessageDialog.new(self, _('How to keep the mini-map on top'), explanation)
        dialog.add_response('ok', _('Got it'))
        dialog.set_default_response('ok')
        dialog.set_close_response('ok')
        dialog.present()

    def set_always_on_top(self, enabled):
        self._always_top = bool(enabled)
        if self.above_check.get_active() != self._always_top:
            self.above_check.set_active(self._always_top)
        if self.get_mapped():
            self._apply_always_top()

    def _top_toggled(self, button):
        value = button.get_active()
        self._always_top = value
        if self.radar.settings.get('pip_always_on_top') != value:
            self.radar._change_setting('pip_always_on_top', value)
        else:
            self._apply_always_top()

    def _zoom_clicked(self, _button, delta):
        if delta > 0 and self.viewport.get_zoom_level() < 17:
            self.map.zoom_in()
        elif delta < 0 and self.viewport.get_zoom_level() > 2:
            self.map.zoom_out()

    def _draw_compact_scale(self, _area, cr, width, height):
        label, pixels = compact_scale(self.viewport.get_latitude(),
                                      self.viewport.get_zoom_level(),
                                      self.radar.settings['speed'])
        cr.set_source_rgba(.05, .08, .10, .67)
        cr.rectangle(0, 0, width - 1, height - 1)
        cr.fill()
        cr.set_source_rgba(1., 1., 1., .95)
        cr.select_font_face('Sans', 0, 0)
        cr.set_font_size(10)
        cr.move_to(6, 12)
        cr.show_text(label)
        x, y = 7, height - 5
        cr.set_line_width(1.25)
        cr.move_to(x, y - 5)
        cr.line_to(x, y)
        cr.line_to(x + pixels, y)
        cr.line_to(x + pixels, y - 5)
        cr.stroke()

    def sync_initial_view(self):
        self._syncing_view = True
        try:
            self.simple_map.set_map_source(self.radar.map_sources[self.radar.settings['map']])
            source = self.radar.viewport
            self.viewport.set_zoom_level(source.get_zoom_level())
            self.map.center_on(source.get_latitude(), source.get_longitude())
        finally:
            self._syncing_view = False
        self.sync_visuals()
        self.sync_aircraft()

    def recenter_location(self, lat, lon):
        """Animate to the user location, not to a new aircraft fix."""
        if not self.get_visible():
            return
        self._center_without_feedback(lat, lon, animated=True)

    def _finish_camera_transition(self, generation):
        if generation == self._camera_generation:
            self._syncing_view = False
        return GLib.SOURCE_REMOVE

    def _center_without_feedback(self, lat, lon, *, animated=False):
        if self._view_timer:
            GLib.source_remove(self._view_timer)
            self._view_timer = 0
        self._camera_generation += 1
        generation = self._camera_generation
        self._syncing_view = True
        if hasattr(self.map, 'stop_go_to'):
            self.map.stop_go_to()
        if animated and hasattr(self.map, 'go_to_full_with_duration'):
            self.map.go_to_full_with_duration(lat, lon, self.viewport.get_zoom_level(), 750)
            GLib.timeout_add(850, self._finish_camera_transition, generation)
        elif animated and hasattr(self.map, 'go_to'):
            self.map.go_to(lat, lon)
            GLib.timeout_add(850, self._finish_camera_transition, generation)
        else:
            try:
                self.map.center_on(lat, lon)
            finally:
                self._syncing_view = False

    def _follow_visible_aircraft(self):
        if not self.radar.follow or not self.radar.selected_hex:
            return
        selected = self._markers.get(self.radar.selected_hex)
        if selected is None:
            return
        lat = selected.marker.get_latitude()
        lon = selected.marker.get_longitude()
        # Do not trigger viewport->radar propagation or extra network calls.
        if abs(self.viewport.get_latitude()-lat) > .000005 or abs(self.viewport.get_longitude()-lon) > .000005:
            self._center_without_feedback(lat, lon)

    def _view_changed(self, *_):
        self.compact_scale.queue_draw()
        if self.settings['tower']:
            self.radar_decoration.queue_draw()
        if self.settings['clock_ring']:
            self.clock_decoration.queue_draw()
        self._airport_view_key = None
        if self._syncing_view or not self.get_visible():
            return
        if self._view_timer:
            GLib.source_remove(self._view_timer)
        self._view_timer = GLib.timeout_add(750, self._propagate_view)

    def _propagate_view(self):
        self._view_timer = 0
        if not self.get_visible():
            return GLib.SOURCE_REMOVE
        self.sync_airports()
        try:
            self.radar.viewport.set_zoom_level(self.viewport.get_zoom_level())
            self.radar.map.center_on(self.viewport.get_latitude(), self.viewport.get_longitude())
            self.radar._view_settled()
            self.radar._persist_map_view()
        except (RuntimeError, ValueError, AttributeError) as exc:
            LOG.debug('Mini-map center synchronization unavailable: %s', exc)
        return GLib.SOURCE_REMOVE

    def sync_aircraft(self):
        """Use existing live markers, including favorite/emergency/sweep state."""
        if not self.get_visible():
            return
        from .ui import AircraftMarker
        from .monitor import is_favorite
        for hexid, marker in list(self._markers.items()):
            if hexid not in self.radar.markers:
                self.marker_layer.remove_marker(marker.marker)
                del self._markers[hexid]
        for hexid, original in self.radar.markers.items():
            if hexid not in self._markers:
                marker = AircraftMarker(original.plane, self._select,
                                        tooltip_enabled=True,
                                        units=self.radar.settings['speed'],
                                        altitude_perspective=self.radar.settings['altitude_perspective'],
                                        on_context=self._context_aircraft,
                                        label_mode=self.radar.settings['marker_label'])
                double = Gtk.GestureClick.new()
                double.set_button(1)
                double.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
                double.connect('pressed', lambda _gesture, count, _x, _y, ident=hexid:
                               self._open_on_double_click(ident) if count == 2 else None)
                marker.button.add_controller(double)
                self.marker_layer.add_marker(marker.marker)
                self._markers[hexid] = marker
            marker = self._markers[hexid]
            marker.altitude_perspective = bool(self.radar.settings['altitude_perspective'])
            marker.set_label_mode(self.radar.settings['marker_label'])
            marker.update(original.plane, original.selected,
                          tooltip_enabled=self.radar.settings['enable_hover'],
                          units=self.radar.settings['speed'], bearing=original.bearing,
                          position_mode='keep')
            marker.marker.set_location(original.marker.get_latitude(),
                                       original.marker.get_longitude())
            marker.set_favorite(is_favorite(self.radar.favorites,
                                            original.plane.registration, hexid))
            marker.set_alert(self.radar._effective_aircraft_alert(original.plane),
                             self.radar.settings['enable_hover'],
                             self.radar.settings['speed'])
        self._follow_visible_aircraft()
        if self.settings['clock_ring']:
            self.clock_decoration.queue_draw()
        self.sync_airports()

    def _select(self, hexid):
        # A single click only selects, no change of window.
        self.radar.select_plane(hexid)
        self.sync_aircraft()
        self.clock_decoration.queue_draw()

    def _open_on_double_click(self, hexid):
        self.radar.select_plane(hexid)
        self.get_application().show_main_window()

    def _context_aircraft(self, hexid, widget, x, y):
        # Same actions as main map, but photo opens above PiP instead of a
        # hidden main window. No new ADS-B or photo calls are made here.
        self.radar.show_aircraft_context_menu(hexid, widget, x, y,
                                             parent_window=self)

    def commit_view(self):
        """Persist the final PiP center even if its debounce has not fired."""
        if self._view_timer:
            GLib.source_remove(self._view_timer)
            self._view_timer = 0
        self.radar._view_suppressed_until = time.monotonic() + .6
        self.radar.viewport.set_zoom_level(self.viewport.get_zoom_level())
        self.radar.map.center_on(self.viewport.get_latitude(), self.viewport.get_longitude())
        self.radar._persist_map_view()

    def _on_close(self, *_):
        self.commit_view()
        if self._view_timer:
            GLib.source_remove(self._view_timer)
            self._view_timer = 0
        self.hide()
        return True
