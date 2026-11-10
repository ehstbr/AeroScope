"""Optional NOAA METAR/SIGMET overlays for Libshumate.

Each map has its own visual layer, while a single WeatherManager shares provider
responses between the main map and PiP. Network IO only runs on worker threads.
"""
from __future__ import annotations
from .i18n import _

import logging
import time
import math
from pathlib import Path

from gi.repository import Gdk, GLib, Gtk, Shumate

from .noaa_schedule import weather_refresh_decision, merge_weather_products
from .weather_data import (fetch_noaa_with_errors, fetch_metar_station,
                           fetch_metar_stations, known_airport_icaos_for_bbox, noaa_bbox,
                           fetch_sigmets_bbox)
from .airport_weather_badge import metar_badge
from .metar_watch import MetarChangeTracker
from .sigmet_readable import describe_sigmet, sigmet_label_point
from .sigmet_style import display_style, sigmet_alpha
from .sigmet_geometry import prepare_sigmets, project, scene_visible, viewport_bounds
from .sigmet_nearby import region_key, region_bbox, sigmets_covering

LOG = logging.getLogger('aeroscope.weather')


class WeatherView:
    """One Cairo SIGMET overlay per map instead of hundreds of PathLayers.

    NOAA geometry is prepared only when the provider response changes.
    Pan/zoom frames cull offscreen shapes and reuse pixel-simplified outlines.
    The original geometry remains available to the map's click hit tester.
    """
    SYMBOL_LIMIT = 36

    def __init__(self, manager, simple_map, overlay, marker_layer):
        self.manager = manager
        self.simple_map = simple_map
        self.viewport = simple_map.get_viewport()
        self.marker_layer = marker_layer
        self.noaa_layers = []  # only METAR and visible SIGMET marker layers
        self._metar_key = None
        self._station_buttons = []
        self._symbols_key = ()
        self._symbol_source = 0
        self._last_draw_log = 0.0
        self._sigmet_marker_layer = None
        self._rendered_scene = None

        self.sigmet_canvas = Gtk.DrawingArea()
        self.sigmet_canvas.set_hexpand(True)
        self.sigmet_canvas.set_vexpand(True)
        self.sigmet_canvas.set_halign(Gtk.Align.FILL)
        self.sigmet_canvas.set_valign(Gtk.Align.FILL)
        # The entire transparent overlay must pass events to the map, whose
        # existing hit tester uses the *original* unsimplified NOAA polygons.
        self.sigmet_canvas.set_can_target(False)
        self.sigmet_canvas.set_draw_func(self._draw_sigmet)
        overlay.add_overlay(self.sigmet_canvas)
        if hasattr(overlay, 'reorder_overlay'):
            overlay.reorder_overlay(self.sigmet_canvas, 0)  # behind controls
        for name in ('latitude', 'longitude', 'zoom-level'):
            self.viewport.connect(f'notify::{name}', self._on_view_changed)
        self.sigmet_canvas.connect('resize', self._on_canvas_resized)
        self.update()

    def _on_canvas_resized(self, *_):
        self._request_symbols()

    def _on_view_changed(self, *_):
        if self.sigmet_canvas.get_visible():
            self.sigmet_canvas.queue_draw()
            # Rebuild only the visible marker subset after the camera settles.
            # Unlike the old PathLayers, this does no widget work per frame.
            self._request_symbols()

    def _put_below_aircraft(self, layer):
        if hasattr(self.simple_map, 'insert_overlay_layer_behind'):
            self.simple_map.insert_overlay_layer_behind(layer, self.marker_layer)
        elif hasattr(self.simple_map.get_map(), 'insert_layer_behind'):
            self.simple_map.get_map().insert_layer_behind(layer, self.marker_layer)
        else:
            self.simple_map.add_overlay_layer(layer)

    def _remove(self, layer):
        if layer is None:
            return
        try:
            self.simple_map.remove_overlay_layer(layer)
        except (RuntimeError, TypeError):
            try:
                self.simple_map.get_map().remove_layer(layer)
            except (RuntimeError, TypeError):
                pass

    def update(self):
        settings = self.manager.radar.settings
        sigmet = bool(settings.get('weather_sigmet') and self.manager.noaa)
        was_visible = self.sigmet_canvas.get_visible()
        data_changed = self._rendered_scene is not self.manager.sigmet_scene
        self.sigmet_canvas.set_visible(sigmet)
        if sigmet:
            if data_changed or not was_visible:
                self.sigmet_canvas.queue_draw()
                self._request_symbols()
        else:
            self._remove_symbols()
        self._rendered_scene = self.manager.sigmet_scene
        if settings.get('weather_metar') and self.manager.noaa is not None:
            self._paint_metars()
        else:
            self._remove_metars()

    def _clear_noaa(self):
        self.sigmet_canvas.set_visible(False)
        self._remove_metars()
        self._remove_symbols()

    def _remove_metars(self):
        if getattr(self, '_metar_layer', None) is not None:
            self._remove(self._metar_layer)
            if self._metar_layer in self.noaa_layers:
                self.noaa_layers.remove(self._metar_layer)
            self._metar_layer = None
        self._metar_key = None
        self._station_buttons = []

    def sync_selection(self):
        """Toggle the selection halo without rebuilding METAR markers."""
        selected = getattr(self.manager.radar, 'selected_weather_station', None)
        code = getattr(selected, 'station', None)
        for station_code, button in self._station_buttons:
            if station_code == code:
                button.add_css_class('selected-location')
            else:
                button.remove_css_class('selected-location')

    def _remove_symbols(self):
        if self._symbol_source:
            GLib.source_remove(self._symbol_source)
            self._symbol_source = 0
        if self._sigmet_marker_layer is not None:
            self._remove(self._sigmet_marker_layer)
            if self._sigmet_marker_layer in self.noaa_layers:
                self.noaa_layers.remove(self._sigmet_marker_layer)
            self._sigmet_marker_layer = None
        self._symbols_key = ()

    def _view_metrics(self, width=None, height=None):
        """Scale and center of the Libshumate viewport in Mercator pixels."""
        widget = self.simple_map.get_map()
        width = width or widget.get_width()
        height = height or widget.get_height()
        if width < 2 or height < 2:
            return None
        lat, lon = self.viewport.get_latitude(), self.viewport.get_longitude()
        zoom = self.viewport.get_zoom_level()
        center_x, center_y = project(lat, lon)
        tile_size = 256
        try:
            source = self.simple_map.get_map_source()
            tile_size = source.get_tile_size() or 256
        except (AttributeError, TypeError):
            pass
        scale = tile_size * (2 ** zoom)
        # Libshumate's coordinates account for the current map allocation;
        # using the exact center also works in a split-pane and in PiP.
        try:
            x, y = self.viewport.location_to_widget_coords(widget, lat, lon)
            if math.isfinite(x) and math.isfinite(y):
                return center_x, center_y, scale, x, y, width, height, zoom
        except (AttributeError, TypeError, ValueError):
            pass
        return center_x, center_y, scale, width / 2, height / 2, width, height, zoom

    def _draw_sigmet(self, _area, cr, width, height):
        scene = self.manager.sigmet_scene
        if not scene or not self.manager.radar.settings.get('weather_sigmet'):
            return
        metrics = self._view_metrics(width, height)
        if metrics is None:
            return
        cx, cy, scale, px, py, width, height, zoom = metrics
        bounds = viewport_bounds(cx, cy, width, height, scale)
        visible = scene_visible(scene, bounds)
        started = time.perf_counter()
        count = 0
        vertices = 0
        cr.save()
        cr.rectangle(0, 0, width, height)
        cr.clip()
        settings = self.manager.radar.settings
        use_colors = settings.get('sigmet_colors', True)
        show_fill = settings.get('sigmet_fill', True)
        tower = settings.get('tower', False)
        selected_advisory = getattr(self.manager.radar, 'selected_sigmet', None)
        # One Cairo surface/GTK widget handles the entire scene. Each NOAA
        # polygon has its own subpath so different hazards can have different
        # colors without reintroducing hundreds of GTK PathLayer widgets.
        # Draw the selected polygon last so it stays noticeable in overlaps.
        ordered = sorted(visible, key=lambda item: item[0].advisory is selected_advisory)
        for shape, rings in ordered:
            count += 1
            selected = shape.advisory is selected_advisory
            visual = display_style(shape.style, use_colors)
            fill_alpha, edge_alpha = sigmet_alpha(selected, tower, filled=show_fill)
            cr.new_path()  # no diagonal connectors between separate advisories
            has_path = False
            for ring, shift in rings:
                points = ring.at_zoom(zoom, tile_size=scale / (2 ** zoom))
                vertices += len(points)
                if len(points) < 3:
                    continue
                for i, (x, y) in enumerate(points):
                    sx = px + (x + shift - cx) * scale
                    sy = py + (y - cy) * scale
                    if i == 0:
                        cr.move_to(sx, sy)
                    else:
                        cr.line_to(sx, sy)
                cr.close_path()
                has_path = True
            if not has_path:
                continue
            r, g, b = visual.rgb
            if fill_alpha > 0:
                # Even-odd supports polygon holes. Filling does not alter
                # source NOAA geometry used for accurate click hit-testing.
                cr.set_fill_rule(1)  # CAIRO_FILL_RULE_EVEN_ODD
                cr.set_source_rgba(r, g, b, fill_alpha)
                cr.fill_preserve()
            cr.set_source_rgba(r, g, b, edge_alpha)
            cr.set_line_width(3.2 if selected else 2.1)
            cr.set_dash([] if selected else [7, 5])
            cr.stroke()
        cr.restore()
        # Sample performance at most once every 10s; no per-frame log IO.
        if time.monotonic() - self._last_draw_log >= 10:
            self._last_draw_log = time.monotonic()
            LOG.debug(_('SIGMET: %d/%d visible advisories, %d vertices after simplification, rendering %.2f ms'), count, len(scene), vertices,
                      (time.perf_counter() - started) * 1000)

    def _request_symbols(self):
        if (self._symbol_source or not self.sigmet_canvas.get_visible()
                or not self.manager.sigmet_scene):
            return
        # Coalesce multiple viewport notifications during drag/animated zoom.
        self._symbol_source = GLib.timeout_add(240, self._sync_symbols)

    def _sync_symbols(self):
        self._symbol_source = 0
        if not self.sigmet_canvas.get_visible() or not self.manager.sigmet_scene:
            return GLib.SOURCE_REMOVE
        metrics = self._view_metrics()
        if metrics is None:
            return GLib.SOURCE_REMOVE
        cx, cy, scale, px, py, width, height, _zoom = metrics
        bounds = viewport_bounds(cx, cy, width, height, scale, padding=40)
        chosen = []
        occupied = set()
        for shape, rings in scene_visible(self.manager.sigmet_scene, bounds):
            if shape.marker is None:
                continue
            lat, lon = shape.marker
            mx, my = project(lat, lon)
            shift = round(cx - mx)
            x = px + (mx + shift - cx) * scale
            y = py + (my - cy) * scale
            if not (8 <= x <= width - 8 and 8 <= y <= height - 8):
                continue
            # One hazard badge per ~80px grid cell keeps dense NOAA responses
            # readable without creating hundreds of clickable GTK buttons.
            cell = (int(x // 82), int(y // 46))
            if cell in occupied:
                continue
            occupied.add(cell)
            chosen.append(shape)
            if len(chosen) == self.SYMBOL_LIMIT:
                break
        colors_enabled = self.manager.radar.settings.get('sigmet_colors', True)
        key = (colors_enabled, tuple(id(shape.advisory) for shape in chosen))
        if key == self._symbols_key:
            return GLib.SOURCE_REMOVE
        self._remove_symbols()
        if not chosen:
            return GLib.SOURCE_REMOVE
        layer = Shumate.MarkerLayer.new(self.viewport)
        for shape in chosen:
            advisory = shape.advisory
            try:
                decoded = describe_sigmet(advisory)
                marker = Shumate.Marker.new()
                button = Gtk.Button(label=f'{decoded.icon} {decoded.short}')
                button.add_css_class('weather-sigmet-marker')
                button.add_css_class('sigmet-' + display_style(
                    shape.style, colors_enabled).key)
                button.set_tooltip_text(_('{value0} · Click for details').format(value0=decoded.title))
                button.connect('clicked', self._show_sigmet, advisory)
                marker.set_child(button)
                marker.set_location(*shape.marker)
                layer.add_marker(marker)
            except (RuntimeError, TypeError, IndexError, AttributeError) as exc:
                LOG.debug(_('SIGMET symbol unavailable: %s'), exc)
        self._put_below_aircraft(layer)
        self._sigmet_marker_layer = layer
        self.noaa_layers.append(layer)
        self._symbols_key = key
        return GLib.SOURCE_REMOVE

    def _paint_noaa(self):
        """Compatibility entry point: repaint, but never recreate paths."""
        self.update()

    def _paint_metars(self):
        metars = self.manager.noaa[0]
        main_map = self.simple_map is self.manager.radar.simple_map
        enabled_airports = bool(self.manager.radar.settings.get('show_airports'))
        key = (main_map, enabled_airports,
               tuple(sorted(self.manager.radar.favorite_stations)),
               tuple((m.station, m.lat, m.lon, m.category, m.observed, m.raw)
                     for m in metars[:250]))
        if key == self._metar_key:
            return
        self._remove_metars()
        layer = Shumate.MarkerLayer.new(self.viewport)
        from .data import AIRPORTS
        fixed_stations = {info[0] for info in AIRPORTS.values()}
        for metar in metars[:250]:
            # The main and PiP now render fixed airports with the same badges.
            # Avoid drawing an overlapping weather-station button on the PiP.
            if metar.station in fixed_stations and enabled_airports:
                continue
            marker = Shumate.Marker.new()
            button = Gtk.Button()
            button.add_css_class('weather-metar-marker')
            button.add_css_class('weather-station-marker')
            if getattr(getattr(self.manager.radar, 'selected_weather_station', None), 'station', None) == metar.station:
                button.add_css_class('selected-location')
            self._station_buttons.append((metar.station, button))
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            icon_file = Path(__file__).resolve().parents[1] / 'assets' / 'weather-station.svg'
            icon = (Gtk.Image.new_from_file(str(icon_file)) if icon_file.is_file()
                    else Gtk.Image.new_from_icon_name('network-wireless-symbolic'))
            icon.set_pixel_size(17)
            icon.add_css_class('weather-station-icon')
            content.append(icon)
            name = Gtk.Label(label=metar.station)
            name.add_css_class('weather-station-code')
            content.append(name)
            if metar.station in self.manager.radar.favorite_stations:
                star = Gtk.Label(label='★')
                star.add_css_class('airport-favorite-star')
                content.append(star)
            badge = metar_badge(metar)
            if badge:
                category = Gtk.Label(label=badge)
                category.add_css_class('weather-station-category')
                content.append(category)
            button.set_child(content)
            button.set_tooltip_text(
                _('Weather station {value0} · {value1} · {value2}').format(value0=metar.station, value1=badge or _('METAR available'), value2=metar.observed or _('Time not provided')))
            button.connect('clicked', self._show_metar, metar)
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)
            right_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            right_click.connect('pressed', lambda gesture, count, x, y, w=button, m=metar:
                                self.manager.radar.show_station_context_menu(m, w, x, y))
            button.add_controller(right_click)
            marker.set_child(button)
            marker.set_location(metar.lat, metar.lon)
            layer.add_marker(marker)
        self._put_below_aircraft(layer)
        self._metar_layer = layer
        self.noaa_layers.append(layer)
        self._metar_key = key

    def _show_sigmet(self, _button, sigmet):
        radar = self.manager.radar
        radar.select_sigmet(sigmet)
        if self.simple_map is not radar.simple_map:
            radar.get_application().show_main_window()

    def _show_metar(self, _button, metar):
        radar = self.manager.radar
        from .data import AIRPORTS
        matching_airport = next((code for code, info in AIRPORTS.items()
                                 if info[0] == metar.station), None)
        if matching_airport:
            radar.select_airport(matching_airport)
            radar._pan_to_aircraft(metar.lat, metar.lon)
        else:
            radar.select_weather_station(metar)
            radar._pan_to_aircraft(metar.lat, metar.lon)
        if self.simple_map is not radar.simple_map:
            radar.get_application().show_main_window()


class WeatherManager:
    NOAA_SECONDS = 900

    def __init__(self, radar):
        self.radar = radar
        self.views = []
        self.noaa = None
        self.sigmet_scene = ()  # prepared exactly once per valid NOAA response
        # Regional queries for selected/favorite/desktop-panel locations.
        # A location can be outside the map or have no METAR at all.
        self._sigmet_regions = {}  # (grid lat,lon) -> (checked, advisories, error)
        self._sigmet_region_queue = []
        self._sigmet_region_busy = None
        self._sigmet_region_next = 0.0
        self._sigmet_region_source = 0
        self._main_sigmet_center = None
        self._main_sigmet_received = 0.0
        self._main_sigmet_snapshot = ()
        self._last_sigmet_active = None
        self._noaa_busy = False
        # Separate deadlines prevent SIGMET-only requests from delaying METAR,
        # and vice versa; background weather polling remains every 15 minutes.
        self._next_noaa = {'metar': 0.0, 'sigmet': 0.0}
        self._last_noaa_request = {'metar': 0.0, 'sigmet': 0.0}
        self._noaa_inflight = frozenset()
        self._manual_noaa_pending = set()
        self.errors = {}
        self._airport_metars = {}  # ICAO -> (checked_monotonic, metar, error)
        self._favorite_tracker = MetarChangeTracker()
        self._favorite_metar_busy = False
        self._favorite_metar_last = 0.0
        self._favorite_metar_errors = {}
        self._airport_pending = set()
        self._airport_batch_missing = set()  # batch omissions are eligible for click lookup
        self._airport_batch_busy = False
        self._airport_batch_checked_at = 0.0
        # Region identity is also per product, so a targeted manual refresh
        # cannot mask the need to fetch the other product after a map move.
        self._last_noaa_center = {'metar': None, 'sigmet': None}
        self._last_noaa_started = {'metar': 0.0, 'sigmet': 0.0}
        self._deferred_noaa_source = 0
        GLib.timeout_add_seconds(30, self.tick)
        GLib.timeout_add_seconds(60, self._refresh_sigmet_validity)
        GLib.idle_add(self.tick)  # fallback: the first successful regional poll triggers sooner

    def attach(self, simple_map, overlay, aircraft_layer):
        view = WeatherView(self, simple_map, overlay, aircraft_layer)
        self.views.append(view)
        return view

    def settings_changed(self):
        if (not self.radar.settings.get('weather_sigmet') and
                getattr(self.radar, 'selected_sigmet', None) is not None):
            self.radar._clear_selected()
        for view in self.views:
            view.update()
        self._next_noaa = {'metar': 0.0, 'sigmet': 0.0}
        self.tick()

    def presentation_changed(self, key):
        """Apply SIGMET-only appearance settings without polling the NOAA API."""
        for view in self.views:
            if key == 'sigmet_colors':
                view._remove_symbols()
                view._request_symbols()
            if view.sigmet_canvas.get_visible():
                view.sigmet_canvas.queue_draw()

    def region_updated(self):
        """A map has just loaded or its center settled after navigation.

        One trigger for the main map and the PiP. The scheduler decides if the
        cached NOAA bbox still covers the region; no HTTP calls while tray-only.
        """
        self.tick()

    def _schedule_deferred_region(self, delay):
        if self._deferred_noaa_source:
            return
        self._deferred_noaa_source = GLib.timeout_add(
            max(1, int(delay * 1000) + 50), self._deferred_region_check)

    def _deferred_region_check(self):
        self._deferred_noaa_source = 0
        self.tick()
        return GLib.SOURCE_REMOVE

    def _visible_viewport(self):
        app = self.radar.get_application()
        pip = getattr(app, 'pip_window', None)
        if pip is not None and pip.get_visible():
            return pip.viewport
        if self.radar.get_visible():
            return self.radar.viewport
        return None

    def _refresh_known_airport_metars(self, center, force=False):
        """Fetch the markers' own NOAA stations as one asynchronous batch.

        The NOAA geo-bbox response alone may omit a known airport, or return a
        different representation. Never require users to click CNF or PLU to
        make their available reports appear on the map.
        """
        if self._airport_batch_busy:
            return
        stations = known_airport_icaos_for_bbox(noaa_bbox(*center))
        now = time.monotonic()
        due = [code for code in stations
               if code not in self._airport_pending and
               (code not in self._airport_metars or
                now - self._airport_metars[code][0] >= (60 if force else self.NOAA_SECONDS))]
        if not due:
            return
        self._airport_batch_busy = True
        self._airport_pending.update(due)
        LOG.info(_('METAR: checking %s local airports by ICAO (batch)'), len(due))
        self.radar._async(
            lambda: fetch_metar_stations(due),
            lambda result, error, codes=tuple(due): self._known_airport_metars_done(codes, result, error))

    def _known_airport_metars_done(self, codes, result, error):
        self._airport_batch_busy = False
        now = time.monotonic()
        rows = {metar.station: metar for metar in (result or [])} if not error else {}
        if error:
            LOG.warning(_('Batch METAR by ICAO: %s'), error)
        else:
            LOG.info(_('METAR: observations at %d/%d known stations'), len(rows), len(codes))
        for code in codes:
            self._airport_pending.discard(code)
            # A failure is not interpreted as a real absence of METAR; retry
            # after 60 s, rather than hammering NOAA every UI update.
            if error:
                previous = self._airport_metars.get(code)
                if previous is None or previous[1] is None:
                    self._airport_metars[code] = (now - self.NOAA_SECONDS + 60,
                                                   None, str(error))
                continue
            previous = self._airport_metars.get(code)
            if code in rows:
                self._airport_batch_missing.discard(code)
            else:
                self._airport_batch_missing.add(code)
            if previous is None or previous[0] < now:
                self._airport_metars[code] = (now, rows.get(code), None)
        if self.radar.settings.get('weather_metar'):
            self.radar._rebuild_airports()
        if self.radar.selected_airport is not None:
            from .data import AIRPORTS
            if AIRPORTS[self.radar.selected_airport][0] in codes:
                self.radar._render_details()
        self._notify_favorites_panel()
        # A pan may have moved to new stations while this batch was in flight.
        GLib.idle_add(self.tick)
        return GLib.SOURCE_REMOVE

    def sigmet_coverage(self, lat, lon, *, request=True):
        """(state, matching advisories), regardless of map SIGMET visibility.

        Status is ready only after a *successful* regional NOAA query. No
        METAR observation and no VFR/IFR categorization is inferred here.
        """
        try:
            key = region_key(lat, lon)
        except (ValueError, TypeError, OverflowError):
            return 'invalid', ()
        now = time.monotonic()
        cached = self._sigmet_regions.get(key)
        if cached is not None and now - cached[0] < self.NOAA_SECONDS:
            checked, bulletins, error = cached
            if error:
                return 'error', ()
            return 'ready', sigmets_covering(bulletins, lat, lon)
        # The map's last successful SIGMET area may already cover this point.
        # Reuse its response rather than issuing duplicate NOAA requests.
        if (self.noaa is not None and self._main_sigmet_center is not None and
                self._main_sigmet_received and
                now - self._main_sigmet_received < self.NOAA_SECONDS):
            south, west, north, east = noaa_bbox(*self._main_sigmet_center)
            if south <= lat <= north and west <= lon <= east:
                return 'ready', sigmets_covering(self._main_sigmet_snapshot, lat, lon)
        if request and not self.radar.demo:
            self._queue_sigmet_region(key)
        return 'loading', ()

    def _queue_sigmet_region(self, key):
        if key == self._sigmet_region_busy or key in self._sigmet_region_queue:
            return
        if len(self._sigmet_region_queue) >= 80:
            return  # limit unfinished requests on very large favorites lists
        self._sigmet_region_queue.append(key)
        self._pump_sigmet_regions()

    def _pump_sigmet_regions(self):
        if self._sigmet_region_busy is not None or self._sigmet_region_source:
            return GLib.SOURCE_REMOVE
        if not self._sigmet_region_queue:
            return GLib.SOURCE_REMOVE
        # At most one regional request per two seconds, well under NOAA limits.
        remaining = self._sigmet_region_next - time.monotonic()
        if remaining > 0:
            self._sigmet_region_source = GLib.timeout_add(
                max(100, int(remaining * 1000) + 50), self._sigmet_pump_ready)
            return GLib.SOURCE_REMOVE
        key = self._sigmet_region_queue.pop(0)
        self._sigmet_region_busy = key
        self._sigmet_region_next = time.monotonic() + 2.0
        self.radar._async(lambda bbox=region_bbox(key): fetch_sigmets_bbox(bbox),
                          lambda result, error, region=key: self._sigmet_region_done(region, result, error))
        return GLib.SOURCE_REMOVE

    def _sigmet_pump_ready(self):
        self._sigmet_region_source = 0
        return self._pump_sigmet_regions()

    def _sigmet_region_done(self, key, advisories, error):
        self._sigmet_region_busy = None
        now = time.monotonic()
        if error:
            LOG.warning(_('SIGMET near a saved location: %s'), error)
            # Retry failures after one minute, but never mislabel them as
            # confirmed absence of an aviation warning.
            self._sigmet_regions[key] = (now - self.NOAA_SECONDS + 60, (), str(error))
        else:
            self._sigmet_regions[key] = (now, tuple(advisories or ()), None)
        self._notify_sigmet_locations()
        # Continue safely after the current GTK event, with rate limiting.
        GLib.idle_add(self._pump_sigmet_regions)
        return GLib.SOURCE_REMOVE

    def _notify_sigmet_locations(self):
        if self.radar.selected_airport is not None or self.radar.selected_weather_station is not None:
            self.radar._render_details()
        self._notify_favorites_panel()

    def _sigmet_target_locations(self):
        """Coordinates of monitored airports, METAR stations and dashboard cards."""
        from .data import AIRPORTS
        locations = []
        if self.radar.selected_airport in AIRPORTS:
            locations.append(AIRPORTS[self.radar.selected_airport][2:4])
        station = self.radar.selected_weather_station
        if station is not None:
            locations.append((station.lat, station.lon))
        dashboard = getattr(self.radar, 'dashboard', None)
        if dashboard is not None:
            for card in dashboard.cards.values():
                if card.kind == 'airport' and card.code in AIRPORTS:
                    locations.append(AIRPORTS[card.code][2:4])
                elif card.kind == 'station':
                    entry = dashboard._entry(card)
                    if entry is not None and 'lat' in entry and 'lon' in entry:
                        locations.append((entry['lat'], entry['lon']))
                    elif card.code in self.radar.favorite_stations:
                        locations.append(self.radar.favorite_stations[card.code])
                    else:
                        metar = self.cached_metar(card.code)
                        if metar is not None:
                            locations.append((metar.lat, metar.lon))
        for code in self.radar.favorite_airports:
            if code in AIRPORTS:
                locations.append(AIRPORTS[code][2:4])
        locations.extend(self.radar.favorite_stations.values())
        return locations

    def _queue_sigmet_targets(self):
        """Request regional SIGMETs without requiring the map layer to be shown."""
        for lat, lon in self._sigmet_target_locations():
            self.sigmet_coverage(lat, lon, request=True)

    def _refresh_sigmet_validity(self):
        """Expire advisories on time, not 15 minutes after their validity ends."""
        if self.radar.demo:
            return GLib.SOURCE_CONTINUE
        signature = []
        for lat, lon in self._sigmet_target_locations():
            state, advisories = self.sigmet_coverage(lat, lon, request=False)
            signature.append((state, tuple((item.name, item.text) for item in advisories)))
        new = tuple(signature)
        if self._last_sigmet_active is not None and new != self._last_sigmet_active:
            self._notify_sigmet_locations()
        self._last_sigmet_active = new
        return GLib.SOURCE_CONTINUE

    def _begin_noaa(self, center, products, *, manual=False):
        """Issue one selective NOAA request, preserving the non-requested data."""
        products = frozenset(products)
        if not products or self._noaa_busy:
            return False
        if self._deferred_noaa_source:
            GLib.source_remove(self._deferred_noaa_source)
            self._deferred_noaa_source = 0
        self._noaa_busy = True
        self._noaa_inflight = products
        now = time.monotonic()
        for product in products:
            self._last_noaa_center[product] = center
            self._last_noaa_started[product] = now
            self._last_noaa_request[product] = now
        metar, sigmet = 'metar' in products, 'sigmet' in products
        if manual:
            names = ' + '.join(p.upper() for p in ('metar', 'sigmet') if p in products)
            self.radar.set_weather_status(
                _('Updating {value0}…').format(value0=names), hold=30)
            if metar:
                # The geo-bbox might omit known airport identifiers, so also
                # refresh those stations in one batch with a 60-second floor.
                self._refresh_known_airport_metars(center, force=True)
                self.refresh_favorite_metars(force=True)
        self.radar._async(
            lambda: fetch_noaa_with_errors(*center, metar=metar, sigmet=sigmet),
            lambda result, error, location=center, products=products, manual=manual:
            self._noaa_done(result, error, location, products, manual=manual))
        return True

    def refresh_now(self, products):
        """User-triggered METAR/SIGMET refresh, independent of ADS-B polling.

        Bypass the 15-minute NOAA cache, but respect a 60-second minimum gap
        per product and coalesce requests while an earlier call is in flight.
        """
        if self.radar.demo:
            self.radar.set_weather_status(_('Weather refresh is unavailable in demo mode.'))
            return False
        requested = set(products)
        if not requested or not requested <= {'metar', 'sigmet'}:
            return False
        viewport = self._visible_viewport()
        if viewport is None:
            self.radar.set_weather_status(_('Open the map to refresh weather data.'))
            return False
        if self._noaa_busy:
            # An existing request for the same kind already satisfies this
            # choice. Queue only products not covered by the in-flight call.
            missing = requested - self._noaa_inflight
            if missing:
                self._manual_noaa_pending.update(missing)
                names = ' + '.join(k.upper() for k in ('metar', 'sigmet') if k in missing)
                self.radar.set_weather_status(
                    _('NOAA {value0}: queued; waiting for the current update…').format(value0=names))
            else:
                names = ' + '.join(k.upper() for k in ('metar', 'sigmet') if k in requested)
                self.radar.set_weather_status(
                    _('NOAA {value0}: update already in progress…').format(value0=names))
            return bool(missing)
        now = time.monotonic()
        allowed = {kind for kind in requested
                   if not self._last_noaa_request[kind] or
                   now - self._last_noaa_request[kind] >= 60}
        if not allowed:
            remaining = max(1, int(min(
                60 - (now - self._last_noaa_request[kind]) for kind in requested)) + 1)
            names = ' + '.join(k.upper() for k in ('metar', 'sigmet') if k in requested)
            self.radar.set_weather_status(
                _('NOAA {value0}: wait {value1} s before refreshing again.').format(
                    value0=names, value1=remaining))
            return False
        center = (viewport.get_latitude(), viewport.get_longitude())
        return self._begin_noaa(center, allowed, manual=True)

    def tick(self):
        dashboard = getattr(self.radar, 'dashboard', None)
        if (not self.radar.demo and
                (self.radar.settings.get('monitor_metar_favorites', True) or
                 (dashboard is not None and dashboard.cards))):
            self.refresh_favorite_metars()
        if not self.radar.demo:
            self._queue_sigmet_targets()
        vp = self._visible_viewport()
        if vp is None:  # no weather polling in tray-only mode
            return GLib.SOURCE_CONTINUE
        now = time.monotonic()
        opts = self.radar.settings
        enabled = [kind for kind in ('metar', 'sigmet')
                   if opts.get('weather_' + kind)]
        if not enabled:
            return GLib.SOURCE_CONTINUE
        if self._noaa_busy:
            # Completion checks for changed viewport or pending manual work.
            return GLib.SOURCE_CONTINUE
        center = (vp.get_latitude(), vp.get_longitude())
        if 'metar' in enabled:
            self._refresh_known_airport_metars(center)
        due = set()
        delay = 0.0
        for product in enabled:
            refresh, remaining = weather_refresh_decision(
                now, self._next_noaa[product], center,
                self._last_noaa_center[product], self._last_noaa_started[product])
            if refresh:
                due.add(product)
            elif remaining:
                delay = remaining if not delay else min(delay, remaining)
        if not due:
            if delay:
                self._schedule_deferred_region(delay)
            return GLib.SOURCE_CONTINUE
        self._begin_noaa(center, due)
        return GLib.SOURCE_CONTINUE

    def _noaa_done(self, result, error, location=None, products=frozenset(('metar', 'sigmet')),
                   *, manual=False):
        self._noaa_busy = False
        self._noaa_inflight = frozenset()
        requested_metar, requested_sigmet = 'metar' in products, 'sigmet' in products
        # Deadline is per product: a SIGMET-only manual update must not make
        # a stale METAR cache appear fresh to the automatic scheduler.
        completed_at = time.monotonic()
        for kind in products:
            self._next_noaa[kind] = completed_at + self.NOAA_SECONDS
        if error is not None:
            LOG.warning(_('NOAA METAR/SIGMET: request failed: %s'), error)
            self.errors.update({kind: str(error) for kind in products})
            if manual:
                names = ' + '.join(k.upper() for k in ('metar', 'sigmet') if k in products)
                self.radar.set_weather_status(
                    _('NOAA {value0}: update failed; previous data kept.').format(value0=names),
                    error=True, hold=8)
        else:
            metars, sigmets, errors = result
            for kind in products:
                if kind in errors:
                    self.errors[kind] = errors[kind]
                else:
                    self.errors.pop(kind, None)
            if errors:
                for kind, detail in errors.items():
                    LOG.warning('NOAA %s: %s', kind.upper(), detail)
            if requested_sigmet and 'sigmet' not in errors and not sigmets:
                LOG.info(_('SIGMET: no active advisories in the requested area'))
            if requested_metar and 'metar' not in errors and not metars:
                LOG.info(_('METAR: no stations with observations in the requested area'))
            # A successful *empty* response is valid; a failed or unrequested
            # product keeps the last good snapshot instead of disappearing.
            self.noaa = merge_weather_products(
                self.noaa, (metars, sigmets), errors,
                metar=requested_metar, sigmet=requested_sigmet)
            if requested_sigmet and 'sigmet' not in errors:
                self._main_sigmet_center = location
                self._main_sigmet_received = completed_at
                self._main_sigmet_snapshot = tuple(sigmets)
                self.sigmet_scene = prepare_sigmets(
                    sigmets, sigmet_label_point, previous=self.sigmet_scene)
                LOG.info(_('SIGMET: %d outlined advisories (of %d received)'),
                         len(self.sigmet_scene), len(sigmets))
            if manual:
                if errors:
                    names = ' + '.join(k.upper() for k in ('metar', 'sigmet') if k in products)
                    self.radar.set_weather_status(
                        _('NOAA {value0}: partially updated; previous data kept.').format(value0=names),
                        error=True, hold=8)
                else:
                    names = ' + '.join(k.upper() for k in ('metar', 'sigmet') if k in products)
                    self.radar.set_weather_status(
                        _('NOAA {value0}: updated.').format(value0=names))
        for view in self.views:
            view.update()
        if self.radar.selected_airport is not None or self.radar.selected_weather_station is not None:
            self.radar._render_details()
        self._notify_favorites_panel()
        if requested_metar and self.radar.settings.get('weather_metar'):
            self.radar._rebuild_airports()
            pip = getattr(self.radar.get_application(), 'pip_window', None)
            if pip is not None and pip.get_visible():
                pip.sync_airports()
        # First service a distinct manual request queued during the previous
        # HTTP call, then the automatic interval/region scheduler.
        queued = tuple(sorted(self._manual_noaa_pending))
        self._manual_noaa_pending.clear()
        if queued:
            self.refresh_now(queued)
        self.tick()
        return GLib.SOURCE_REMOVE

    def sigmet_at_location(self, lat, lon):
        """Hit test original NOAA rings, first eliminating offscreen candidates.

        A cached Mercator bbox makes clicks cheap even with hundreds of
        advisories. The final exact point-in-polygon retains source precision.
        """
        from .sigmet_readable import sigmet_at_point
        if not self.sigmet_scene:
            return None
        try:
            px, py = project(lat, lon)
        except (TypeError, ValueError):
            return None
        for shape in reversed(self.sigmet_scene):
            x_shift = round(px - (shape.bbox[0] + shape.bbox[2]) / 2)
            if not (shape.bbox[0] + x_shift <= px <= shape.bbox[2] + x_shift
                    and shape.bbox[1] <= py <= shape.bbox[3]):
                continue
            if sigmet_at_point((shape.advisory,), lat, lon):
                return shape.advisory
        return None

    def notification_metar_codes(self):
        """Only actual favorites are allowed to emit change notifications."""
        from .data import AIRPORTS
        airports = {AIRPORTS[code][0] for code in self.radar.favorite_airports if code in AIRPORTS}
        return airports | set(self.radar.favorite_stations)

    def favorite_metar_codes(self):
        # Floating panels share the same NOAA batch and cache, even when they
        # are not part of the user's persistent Favorites collection.
        dashboard = getattr(self.radar, 'dashboard', None)
        favorites = (self.notification_metar_codes()
                     if self.radar.settings.get('monitor_metar_favorites', True) else set())
        return favorites | (dashboard.station_codes() if dashboard else set())

    def favorites_changed(self):
        """Synchronize membership and get fresh METAR data without a timer delay."""
        codes = self.favorite_metar_codes()
        self._favorite_tracker.retain(codes)
        for code in tuple(self._favorite_metar_errors):
            if code not in codes:
                self._favorite_metar_errors.pop(code, None)
        self._favorite_metar_last = 0.0
        if not self.radar.demo:
            self._queue_sigmet_targets()
        dashboard = getattr(self.radar, 'dashboard', None)
        if (not self.radar.demo and
                (self.radar.settings.get('monitor_metar_favorites', True) or
                 (dashboard is not None and dashboard.cards))):
            GLib.idle_add(self.refresh_favorite_metars)

    def _notify_favorites_panel(self):
        dashboard = getattr(self.radar, 'dashboard', None)
        if dashboard is not None:
            dashboard.update_weather()
        pip = getattr(self.radar.get_application(), 'pip_window', None)
        if pip is not None and pip.get_visible():
            pip.sync_airports()  # Cached NOAA badges only; no network request.
        panel = getattr(self.radar, 'monitor_panel', None)
        if panel is not None and self.radar.get_mapped():
            if panel.switch.get_visible_child_name() == 'favorites':
                panel._render_favorites()

    def favorite_metar_status(self, code):
        """Return the last known bulletin and its retrieval state without network IO."""
        key = str(code).strip().upper()
        report = self.cached_metar(key)
        if key in self._favorite_metar_errors:
            return 'error', report, self._favorite_metar_errors[key]
        if key in self._airport_metars:
            cached = self._airport_metars[key]
            return 'ready' if cached[1] is not None else 'missing', report, cached[2]
        if self._favorite_metar_busy or key in self._airport_pending:
            return 'loading', report, None
        return 'unknown', report, None

    def refresh_favorite_metars(self, force=False):
        """One batch per 15 min; independent of radar viewport and NOAA map overlays."""
        codes = self.favorite_metar_codes()
        self._favorite_tracker.retain(codes)
        if not codes or self._favorite_metar_busy or self.radar.demo:
            return GLib.SOURCE_CONTINUE
        now = time.monotonic()
        # The refresh button cannot hammer NOAA more frequently than 60 s.
        minimum = 60 if force else self.NOAA_SECONDS
        if self._favorite_metar_last and now - self._favorite_metar_last < minimum:
            return GLib.SOURCE_CONTINUE
        due = []
        valid_cached = {}
        for code in sorted(codes):
            cache = self._airport_metars.get(code)
            if not force and cache and now - cache[0] < self.NOAA_SECONDS:
                valid_cached[code] = cache[1]
            else:
                due.append(code)
        self._favorite_metar_last = now
        if not due:
            self._favorite_metar_process(valid_cached, {})
            return GLib.SOURCE_CONTINUE
        self._favorite_metar_busy = True
        LOG.info(_('Favorite METAR: checking %d airport/station codes'), len(due))

        station_positions = dict(self.radar.favorite_stations)

        def work():
            # NOAA caps individual batch size. Stay polite if the user has many favorites.
            observations, failures = {}, {}
            for offset in range(0, len(due), 50):
                group = due[offset:offset+50]
                try:
                    for report in fetch_metar_stations(group, fallback_positions=station_positions):
                        observations[report.station] = report
                except (OSError, ValueError, TypeError) as exc:
                    failures.update({station: str(exc) for station in group})
                if offset + 50 < len(due):
                    time.sleep(1)
            return observations, failures

        self.radar._async(work, lambda result, error, requested=tuple(due), reused=valid_cached:
                          self._favorite_metar_done(requested, reused, result, error))
        return GLib.SOURCE_CONTINUE

    def _favorite_metar_done(self, requested, reused, result, error):
        self._favorite_metar_busy = False
        reports, failures = result if result is not None else ({}, {})
        if error is not None:
            failures = {code: str(error) for code in requested}
        now = time.monotonic()
        fresh = dict(reused)
        active_codes = self.favorite_metar_codes()
        for code in requested:
            if code not in active_codes:
                continue  # Removed while NOAA was responding.
            if code in failures:
                self._favorite_metar_errors[code] = failures[code]
                # Retry only after a backoff, rather than every GTK redraw.
                if not any(c in self._airport_metars for c in (code,)):
                    self._airport_metars[code] = (now - self.NOAA_SECONDS + 60, None, failures[code])
                LOG.warning(_('Favorite METAR {value0}: {value1}').format(
                    value0=code, value1=failures[code]))
                continue
            self._favorite_metar_errors.pop(code, None)
            report = reports.get(code)
            self._airport_metars[code] = (now, report, None)
            fresh[code] = report
        self._favorite_metar_process(fresh, failures)
        if self.radar.settings.get('weather_metar'):
            self.radar._rebuild_airports()
        if self.radar.selected_airport is not None:
            from .data import AIRPORTS
            if AIRPORTS[self.radar.selected_airport][0] in requested:
                self.radar._render_details()
        if self.radar.selected_weather_station is not None:
            code = self.radar.selected_weather_station.station
            if code in reports:
                self.radar.selected_weather_station = reports[code]
                self.radar._render_details()
        self._notify_favorites_panel()
        return GLib.SOURCE_REMOVE

    def _favorite_metar_process(self, reports, failures):
        current = self.favorite_metar_codes()
        for code, report in reports.items():
            if code not in current or code in failures:
                continue
            changed, previous_category = self._favorite_tracker.observe(code, report)
            if (not changed or code not in self.notification_metar_codes() or
                    not self.radar.settings.get('monitor_metar_favorites', True) or
                    not self.radar.settings.get('notify_metar_changes', True)):
                continue
            category = report.category or 'N/D'
            old = str(previous_category or 'N/D')
            transition = (old + ' → ' + category) if old != category else category
            details = (report.raw or _('New weather observation')).strip()[:240]
            message = f'{transition} · {report.observed or "UTC"}\n{details}'
            self.radar.emit_monitor_alert(
                _('METAR updated · {value0}').format(value0=code), message,
                notification_id='metar-' + code, action='app.monitor', sound=False)
        self._notify_favorites_panel()

    def cached_metar(self, station):
        """Read last NOAA station record without starting any network request."""
        key = str(station or '').strip().upper()
        value = self._airport_metars.get(key)
        if value and value[1] is not None:
            return value[1]
        if self.noaa is not None and self.noaa[0]:
            for metar in self.noaa[0]:
                if metar.station == key:
                    return metar
        return None

    def get_airport_metar(self, station):
        """Return cached status immediately; initiate a background NOAA lookup if needed."""
        key = str(station).strip().upper()
        if len(key) != 4 or not key.isalnum():
            return 'invalid', None, None
        now = time.monotonic()
        value = self._airport_metars.get(key)
        if value and now - value[0] < self.NOAA_SECONDS and not (
                value[1] is None and key in self._airport_batch_missing):
            return ('error' if value[2] else 'ready'), value[1], value[2]
        # Clicking a station in an already populated NOAA regional overlay
        # must not generate another request simply because the separately
        # maintained ICAO lookup cache has no entry for that station.
        if self.noaa is not None and 'metar' not in self.errors:
            for metar in self.noaa[0]:
                if metar.station == key:
                    return 'ready', metar, None
        if key not in self._airport_pending:
            self._airport_batch_missing.discard(key)
            self._airport_pending.add(key)
            self.radar._async(lambda: fetch_metar_station(key),
                              lambda result, error, code=key: self._airport_done(code, result, error))
        return 'loading', None, None

    def _airport_done(self, code, result, error):
        self._airport_pending.discard(code)
        self._airport_metars[code] = (time.monotonic(), result, str(error) if error else None)
        if error:
            LOG.warning(_('Airport METAR %s: %s'), code, error)
        if self.radar.selected_airport is not None:
            from .data import AIRPORTS
            if AIRPORTS.get(self.radar.selected_airport, ('',))[0] == code:
                self.radar._render_details()
        if self.radar.settings.get('weather_metar') and result is not None:
            self.radar._rebuild_airports()
        if (self.radar.selected_weather_station is not None and
                self.radar.selected_weather_station.station == code):
            if result is not None:
                self.radar.selected_weather_station = result
            self.radar._render_details()
        self._notify_favorites_panel()
        return GLib.SOURCE_REMOVE
