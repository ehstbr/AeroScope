"""Interface GTK4 + Libadwaita + libshumate do AeroScope.

Aplicativo Linux com Libadwaita, sem PHP; WebKitGTK é opcional para páginas externas.
"""
from __future__ import annotations
from .i18n import _
import math
import logging
import re
import datetime
import sys
import time
import shutil
import subprocess
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Shumate', '1.0')
from gi.repository import Adw, Gtk, Gdk, Gio, GLib, Shumate, Pango

try:
    gi.require_version('Geoclue', '2.0')
    from gi.repository import Geoclue
except (ValueError, ImportError):
    Geoclue = None

from .data import (Aircraft, AIRPORTS, demo_aircraft, fetch_area, fetch_plane,
                   geocode_city, geolocate_by_public_ip, find_airport, fetch_history_index, fetch_history_path,
                   fetch_photo_details, download_thumbnail, fetch_visible_area, airport_board_url,
                   fetch_live_route, fetch_history_replay, search_historical_flights, RateLimitError)
from .aircraft_art import aircraft_name, aircraft_category, aircraft_kind, paint_aircraft, paint_replay_aircraft, paint_favorite_star
from .alerts import classify_alert
from .emergency_match import effective_alert
from .marker_labels import aircraft_marker_caption, VALID_MODES
from .monitor import load_favorites, save_favorites, add_favorite, is_favorite
from .airport_favorites import load_airport_favorites, save_airport_favorites
from .station_favorites import load_station_favorites, save_station_favorites
from .monitor_ui import SidebarMonitor
from .context_tooltips import protect_context_menu
from .motion import (PositionTransition, transition_allowed, startup_poll_interval,
                     flight_animation_duration, RequestLatencyTracker)
from .preferences import PreferencesWindow
from .settings import APP_ID, GITHUB, VERSION, load, save, clear_cache
from .autostart import configure as configure_autostart
from .regional_poll import regional_mode
from .map_view import load_view, save_view
from .residency import close_behavior
from .location_policy import system_location_status, should_suggest_ip
from .location_dialog import IpLocationDialog
from .logging_utils import configure_logging
from .search_suggestions import (local_suggestions, city_suggestions, historical_suggestions,
                                 grouped_suggestions, normalized, classify_aircraft_identifier, SearchSuggestion)
from .geoview import coverage_for_view, fit_trajectory, is_on_screen, distance_nm, viewport_inside_radius
from .routes import RouteCache, great_circle_points, map_segments, ProbableRoute, route_has_geometry
from .playback import HistoricalReplay
from .replay_chart import plot_chart, chart_hit_fraction, time_for_fraction
from .metar_readable import describe_metar
from .sidebar_layout import (needs_wrap, detail_needs_stacking,
                             SIDEBAR_NATURAL_WIDTH_CHARS)
from .dashboard import DashboardController
from .keyboard_shortcuts import keyboard_command, MENU_ACCELERATORS
from .keyboard_pan import KeyboardPan, KEY_DIRECTIONS
from .map_orientation import lock_north_up
from .tower_radar import (bearing_on_screen, crossed_clockwise, crossed_moving_target, ring_label,
                          meters_per_pixel, full_map_radius, clock_hour_bearings,
                          clock_ring_radius, ring_label_anchor)

DEFAULT_CENTER = (-20.1389, -44.8839)
ROOT = Path(__file__).resolve().parent.parent
EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix='aeroscope')
PHOTO_LOG = logging.getLogger('aeroscope.photos')


def format_speed(knots, main='kmh'):
    if knots is None:
        return _('Not available')
    units = {'kmh': (knots*1.852, 'km/h'),
             'kt': (knots, 'kt'), 'mph': (knots*1.15077945, 'mph')}
    primary = units.get(main, units['kmh'])
    return f'{round(primary[0])} {primary[1]}'


def speed_details(knots, main='kmh'):
    if knots is None:
        return _('Not available')
    return _('{value0} · {value1} knots · {value2} km/h · {value3} mph').format(value0=format_speed(knots, main), value1=round(knots), value2=round(knots * 1.852), value3=round(knots * 1.15077945))


def haversine_nm(a, b, lat, lon):
    p, q = math.radians(a-lat), math.radians(b-lon)
    h = math.sin(p/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(a))*math.sin(q/2)**2
    return 3440.065 * 2 * math.asin(min(1, math.sqrt(h)))



def make_label(value, css=None, wrap=False):
    label = Gtk.Label(label=str(value), xalign=0)
    # GTK labels with large natural widths can silently resize the parent
    # Gtk.Paned, even when they are inside a scrolled sidebar. Cap all long
    # sidebar labels, not just the METAR field that first exposed the bug.
    if needs_wrap(value, wrap):
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_width_chars(1)
        label.set_max_width_chars(SIDEBAR_NATURAL_WIDTH_CHARS)
    else:
        label.set_wrap(False)
    if css:
        label.add_css_class(css)
    return label


def icon_button(icon, tip, callback, css=None):
    b = Gtk.Button(icon_name=icon)
    b.set_tooltip_text(tip)
    if css:
        b.add_css_class(css)
    b.connect('clicked', callback)
    return b


def append_menu_action(menu, label, action):
    """Show existing shortcuts in the native GTK4 hamburger menu.

    Gio.MenuModel items can advertise an ``accel`` label without registering a
    second keyboard handler.  This preserves the window's Alt handling and
    system Ctrl-based editing commands while displaying the key at the right.
    """
    accel = MENU_ACCELERATORS.get(action)
    if not accel:
        menu.append(label, action)
        return
    item = Gio.MenuItem.new(label, action)
    item.set_attribute_value('accel', GLib.Variant.new_string(accel))
    menu.append_item(item)


def line_row(title, value):
    """Inspector field row without a long value stretching the sidebar.

    One-line facts remain side by side. Long METAR reports, alert descriptions
    and aircraft attributes become a two-line/paragraph row with normal word
    wrapping, rather than forcing the whole map to shrink horizontally.
    """
    stacked = detail_needs_stacking(title, value)
    h = Gtk.Box(orientation=(Gtk.Orientation.VERTICAL if stacked else
                             Gtk.Orientation.HORIZONTAL), spacing=(3 if stacked else 10))
    h.add_css_class('sidebar-detail-row')
    if stacked:
        h.add_css_class('sidebar-detail-long')
    text = make_label(title, 'dim-label', wrap=stacked)
    text.set_valign(Gtk.Align.START)
    text.set_hexpand(not stacked)
    h.append(text)
    v = make_label(value, wrap=True)
    v.set_hexpand(True)
    v.set_halign(Gtk.Align.FILL)
    v.set_xalign(0 if stacked else 1)
    v.set_valign(Gtk.Align.START)
    v.add_css_class('numeric')
    h.append(v)
    return h


class AircraftMarker:
    """Clickable native map marker with an aircraft-category-specific silhouette."""
    def __init__(self, plane: Aircraft, on_click, tooltip_enabled=True, units='kmh',
                 altitude_perspective=True, on_context=None, label_mode='off'):
        self.plane = plane
        self.selected = False
        self.highlighted = False
        self.favorite = False
        self.alert_override = None
        self.bearing = plane.track
        self.altitude_perspective = altitude_perspective
        self.label_mode = label_mode if label_mode in VALID_MODES else 'off'
        self.transition = None
        self.last_fix_at = time.monotonic()
        self.marker = Shumate.Marker.new()
        self.marker.set_location(plane.lat, plane.lon)
        self.area = Gtk.DrawingArea()
        self.area.set_content_width(100 if self.label_mode != 'off' else 56)
        self.area.set_content_height(92 if self.label_mode != 'off' else 56)
        self.area.set_draw_func(self.draw)
        self.button = Gtk.Button(child=self.area)
        self.button.add_css_class('aircraft-marker')
        # A hand is already used by the map for dragging; a loupe distinguishes
        # opening the aircraft details and centering the map on its location.
        self.button.set_cursor_from_name('zoom-in')
        self.button.set_tooltip_text(self._tooltip(plane, units) if tooltip_enabled else None)
        self.button.connect('clicked', lambda *_: on_click(self.plane.hex))
        if on_context is not None:
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)
            right_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            right_click.connect('pressed', lambda gesture, count, x, y:
                                on_context(self.plane.hex, self.button, x, y))
            self.button.add_controller(right_click)
        self.marker.set_child(self.button)

    @staticmethod
    def _tooltip(plane, units='kmh', alert=None):
        alert = alert or classify_alert(plane.squawk, plane.emergency)
        warning = f'\n{alert.label}' if alert.level != 'none' else ''
        return (_('{value0} · {value1}\nRegistration: {value2}\nAltitude: {value3} · Velocidade: {value4}\nRumo: {value5}° · Position: {value6:.3f}, {value7:.3f}{value8}\nClique para ver os detalhes').format(value0=plane.flight or plane.registration or plane.hex.upper(), value1=aircraft_name(plane.model), value2=plane.registration or '—', value3=plane.altitude, value4=format_speed(plane.speed_kts, units), value5=round(plane.track), value6=plane.lat, value7=plane.lon, value8=warning))

    def draw(self, _area, cr, width, height):
        # Keep the aircraft centered over its geographical point when a caption
        # increases the canvas size. Only the caption is stationary horizontally;
        # the aircraft silhouette continues to rotate by its actual bearing.
        xshift, yshift = (width - 56) / 2, (height - 56) / 2
        cr.save()
        cr.translate(xshift, yshift)
        paint_aircraft(cr, self.plane.model, self.bearing, selected=self.selected,
                       highlighted=self.highlighted,
                       alert_level=(self.alert_override or
                                    classify_alert(self.plane.squawk, self.plane.emergency)).level,
                       altitude_ft=(self.plane.altitude_ft if self.altitude_perspective else float('nan')))
        if self.favorite:
            paint_favorite_star(cr)
        cr.restore()
        caption = aircraft_marker_caption(self.plane, self.label_mode)
        if caption:
            # Compact dark pill readable on either a light or dark map source.
            cr.save()
            cr.select_font_face('Sans', 0, 1)
            cr.set_font_size(10.5)
            ext = cr.text_extents(caption)
            text_width = min(width - 10, ext.width)
            left = (width - text_width) / 2
            top = height - 19
            cr.new_path()
            cr.rectangle(left - 5, top, text_width + 10, 17)
            cr.set_source_rgba(.055, .095, .135, .88)
            cr.fill_preserve()
            cr.set_source_rgba(.73, .88, .96, .82)
            cr.set_line_width(.7)
            cr.stroke()
            cr.set_source_rgb(.98, .99, 1.0)
            cr.move_to(left, height - 7)
            cr.show_text(caption)
            cr.restore()

    def set_label_mode(self, mode):
        mode = mode if mode in VALID_MODES else 'off'
        if self.label_mode == mode:
            return
        self.label_mode = mode
        self.area.set_content_width(100 if mode != 'off' else 56)
        self.area.set_content_height(92 if mode != 'off' else 56)
        self.area.queue_draw()

    def update(self, plane, selected, tooltip_enabled=True, units='kmh', bearing=None,
               position_mode='keep', timestamp=None, duration=None):
        """Refresh aircraft metadata without resetting an ongoing animation.

        position_mode: keep (UI-only change), snap, or smooth (new ADS-B fix).
        """
        now = time.monotonic() if timestamp is None else timestamp
        self.plane = plane
        self.selected = selected
        self.bearing = plane.track if bearing is None else bearing
        target = (plane.lat, plane.lon)
        if position_mode == 'smooth':
            # The marker can be halfway through an older move; use its currently
            # displayed position and safely restart from that exact location.
            start = (self.marker.get_latitude(), self.marker.get_longitude())
            age = now - self.last_fix_at
            if transition_allowed(start, target, age):
                self.transition = PositionTransition(start, target, now,
                                                     duration=duration if duration is not None else 27.6)
            else:
                self.transition = None
                self.marker.set_location(*target)
            self.last_fix_at = now
        elif position_mode == 'snap':
            self.transition = None
            self.marker.set_location(*target)
            self.last_fix_at = now
        # 'keep' preserves current coordinates and animation across UI redraws.
        self.button.set_tooltip_text(
            self._tooltip(plane, units, self.alert_override) if tooltip_enabled else None)
        self.area.queue_draw()

    def set_alert(self, alert, tooltip_enabled=True, units='kmh'):
        if self.alert_override != alert:
            self.alert_override = alert
            self.button.set_tooltip_text(
                self._tooltip(self.plane, units, alert) if tooltip_enabled else None)
            self.area.queue_draw()

    def animation_step(self, now):
        """Advance one screen-only step; return True while still moving."""
        if self.transition is None:
            return False
        point, finished = self.transition.sample(now)
        self.marker.set_location(*point)
        if finished:
            self.transition = None
        return not finished

    def set_favorite(self, value):
        if self.favorite != bool(value):
            self.favorite = bool(value)
            self.area.queue_draw()

    def stop_animation(self):
        self.transition = None
        self.marker.set_location(self.plane.lat, self.plane.lon)

    def set_selected(self, value):
        if self.selected != value:
            self.selected = value
            self.area.queue_draw()

    def set_highlighted(self, value):
        if self.highlighted != value:
            self.highlighted = value
            self.area.queue_draw()


class RadarWindow(Adw.ApplicationWindow):
    def __init__(self, app, demo=False):
        super().__init__(application=app, title='AeroScope', default_width=1250, default_height=800)
        self.demo = bool(demo)
        self.settings = load()
        self.favorites = load_favorites()
        self.favorite_airports = load_airport_favorites()
        self.favorite_stations = load_station_favorites()
        self.monitor_panel = None
        self._apply_theme()
        self._restored_map_view = load_view()
        self.center = self._restored_map_view[:2] if self._restored_map_view else DEFAULT_CENTER
        self.center_name = (_('Last viewed area') if self._restored_map_view else
                            _('Divinópolis, MG · initial position'))
        self.connect('close-request', self._on_close_requested)
        self.poll_seconds = self.settings['refresh']
        self._regional_tracking_started = not getattr(app, '_starting_background', False)
        self._regional_mode = None
        self._successful_polls = 0
        self._warmup_failed = False
        self._startup_dialog = None
        self._startup_label = None
        self._startup_fraction = None
        self._startup_finished = False
        self._next_poll_due = float('inf')
        # Request times are measured on completed successful responses, then
        # used to animate until just before the *next expected response*.
        self._request_latency = RequestLatencyTracker()
        self._active_request_started = 0.0
        self._animation_window = flight_animation_duration(self.poll_seconds)
        self.tick = 0
        self.busy = False
        self.search_busy = False
        # Search suggestions use existing radar data; city lookups are debounced,
        # async, cached for the session, and never run for every keystroke.
        self._search_city_cache = {}
        self._history_search_cache = {}
        self._history_search_errors = {}
        self._history_search_pending = set()
        self._history_search_metadata = {}
        self._search_city_error = None
        self._search_timer = 0
        self._search_generation = 0
        self._city_fetch_inflight = False
        self._last_city_request = 0.0
        self._suggestion_rows = []
        self._ignore_search_text = None
        # Once an item has been chosen, background refreshes must not reopen
        # the suggestions until the user edits the search field again.
        self._search_committed = False
        self.request_number = 0
        self.records: dict[str, Aircraft] = {}
        self._last_live_snapshot_at = 0.0
        self.markers: dict[str, AircraftMarker] = {}
        self.trails = defaultdict(lambda: deque(maxlen=45))
        self.selected_hex = None
        self.selected_sigmet = None  # NOAA weather advisory displayed in the inspector
        self.selected_weather_station = None  # NOAA station outside the airport directory
        self.selected_airport = None
        # Selection from the worldwide emergency feed is not necessarily in
        # the current 250 NM regional feed. Keep its last observed fix separate
        # from self.records (which must contain only real regional results).
        self._global_selected_aircraft = None
        self._global_selected_marker = None
        self.photo_info = {}
        self.photo_widgets = {}  # one decoded texture + GTK photo block per aircraft
        self.photo_pending = set()
        self.photo_errors = {}
        self.history_info = {}
        self.history_pending = set()
        self.archive_layers = []
        self.current_archive_id = None
        self.replay_track = None
        self.replay_time = None
        self.replay_running = False
        self.replay_rate = 1
        self._replay_last_tick = 0.0
        self._replay_timer_id = 0
        self._replay_slider_changing = False
        self._replay_rendered_at = None
        self._replay_chart_last_draw = 0.0
        self.replay_heading = 0.0
        self.replay_model = ''
        self.replay_aircraft_info = None
        self.replay_archive_info = None
        self.route_cache = RouteCache(success_ttl=1800, miss_ttl=120)
        self.route_pending = set()
        self.route_visible = False
        self._route_display_key = None
        self._route_camera = False
        self._route_previous_view = None
        self._routes_cooldown_until = 0.0
        self.follow = False
        self.location_request = None
        self._last_system_fix = None  # recent GeoClue fix for repeat recentering
        self._last_location_fix = None  # last GeoClue/IP map fix in this session
        self._ip_location_pending = False
        self._ip_dialog = None
        self._location_fallback_offered = False
        self._ip_suggestion_waiting = False
        self._location_request_manual = False
        self._geo_timeout_id = 0
        self._view_timer = 0
        self._view_suppressed_until = 0.0
        self._camera_transition_until = 0.0
        self._camera_transition_generation = 0
        self._keyboard_pan = KeyboardPan()
        self._keyboard_pan_timer = 0
        self._view_dirty = False
        self._pending_refresh = False
        self._history_camera = False
        self._last_view_signature = None
        self._coverage = None
        self._coverage_complete = True
        self._query_anchor = None
        self._pending_anchor = None
        self._last_api_request = 0.0
        self._cooldown_until = 0.0
        self.bearings = {}
        self.hover_hex = None
        self._animation_source = 0
        self._sweep_source = 0
        self._sweep_start_at = time.monotonic()
        self._sweep_previous_angle = 0.0
        self._sweep_pending = {}  # ICAO24 -> latest confirmed (plane, bearing)
        self._sweep_virtual = {}  # ICAO24 -> internal interpolation; not drawn
        self._dashboard_mode = False
        self._build_ui()
        # Gtk.SearchEntry may acquire the initial keyboard focus as the first
        # focusable control in the sidebar. Give it to the map on first display;
        # Alt shortcuts still work if the user later focuses the search field.
        self._first_map_focus_id = self.connect('map', self._focus_map_on_first_show)
        self.connect('notify::fullscreened', self._on_fullscreen_changed)
        GLib.timeout_add(400, self._restore_dashboard_fullscreen)
        # Hide search suggestions if another application gains focus.
        self.connect('notify::is-active', self._window_activity_changed)
        self._load_style()
        self._update_tower_sweep_timer()
        self._last_poll = time.monotonic()
        if self.settings['startup_splash'] and self._regional_tracking_started:
            GLib.timeout_add(150, self._open_startup_dialog)
            # Timeout is a safety net: a slow/missing API never traps the UI.
            GLib.timeout_add_seconds(22, self._startup_watchdog)
        if self._regional_tracking_started:
            GLib.timeout_add(900, self._initial_refresh)
        # One non-blocking worldwide emergency check and a favorite check run
        # during initial radar warm-up. This also runs if the splash is hidden.
        # Periodic global checking remains independently opt-in.
        if not self.demo and self.monitor_panel is not None:
            GLib.timeout_add(1700, self.monitor_panel.start_initial_checks)
        GLib.timeout_add(250, self._timer_refresh)
        # GeoClue works on multiple Linux desktops. IP lookup is NEVER automatic:
        # on failure we may *offer* it, but only user consent starts the request.
        if not self.demo and self._regional_tracking_started and self._restored_map_view is None:
            # Do not override the saved view with automatic GeoClue lookup.
            GLib.timeout_add_seconds(2, self._startup_locate)

    def _focus_map_on_first_show(self, *_args):
        self.disconnect(self._first_map_focus_id)
        GLib.idle_add(self._focus_map_if_search_selected)

    def _focus_map_if_search_selected(self):
        focused = self.get_focus()
        while focused is not None:
            if focused is self.search:
                self.map.grab_focus()
                break
            focused = focused.get_parent()
        return GLib.SOURCE_REMOVE

    def _restore_dashboard_fullscreen(self):
        if self.dashboard.restore_fullscreen and not self._dashboard_mode:
            self.set_dashboard_mode(True)
        return GLib.SOURCE_REMOVE

    def _on_fullscreen_changed(self, *_args):
        # If the compositor exits fullscreen by its own shortcut, keep UI and
        # saved state consistent with the actual Gtk.Window:fullscreened value.
        actual = self.is_fullscreen()
        if actual != self._dashboard_mode:
            self._set_dashboard_visual(actual)
            self.dashboard.set_fullscreen_saved(actual)

    def _set_dashboard_visual(self, enabled):
        self._dashboard_mode = bool(enabled)
        self.main_header.set_visible(not enabled)
        self.main_sidebar.set_visible(not enabled)
        self.exit_dashboard_button.set_visible(enabled)
        if enabled:
            self._sidebar_width_before_dashboard = self.main_pane.get_position()
            self.main_pane.set_position(0)
        else:
            self.main_pane.set_position(getattr(
                self, '_sidebar_width_before_dashboard', 345))
        # The map allocation changes after Gtk.Paned and the top bar are hidden.
        GLib.timeout_add(350, self.dashboard.relayout)

    def set_dashboard_mode(self, enabled):
        enabled = bool(enabled)
        if enabled != self._dashboard_mode:
            self._set_dashboard_visual(enabled)
        self.dashboard.set_fullscreen_saved(enabled)
        if enabled:
            self.fullscreen()
        else:
            self.unfullscreen()

    def toggle_dashboard_mode(self):
        self.set_dashboard_mode(not self._dashboard_mode)

    def _dashboard_escape(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape and self._dashboard_mode:
            self.set_dashboard_mode(False)
            return True
        return False

    def _keyboard_pan_pressed(self, keyval, state):
        """Arrow panning only when the map, not the text or lists, has focus."""
        key = Gdk.keyval_name(keyval)
        if (key not in KEY_DIRECTIONS or self.get_focus() is not self.map or
                state & (Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.CONTROL_MASK |
                         Gdk.ModifierType.SUPER_MASK)):
            return False
        if not self._keyboard_pan.held:
            # Manual navigation takes precedence over auto-follow/go-to.
            self.follow = False
            self._camera_transition_generation += 1
            self._camera_transition_until = 0.0
            self._view_suppressed_until = 0.0
            if hasattr(self.map, 'stop_go_to'):
                self.map.stop_go_to()
        self._keyboard_pan.press(key, time.monotonic())
        if not self._keyboard_pan_timer:
            self._keyboard_pan_timer = GLib.timeout_add(16, self._keyboard_pan_tick)
        return True

    def _keyboard_pan_released(self, _controller, keyval, _keycode, _state):
        self._keyboard_pan.release(Gdk.keyval_name(keyval))

    def _keyboard_pan_tick(self):
        # Don't leave a key stuck after Alt+Tab or focus change.
        if self.get_focus() is not self.map or not self.is_active():
            self._keyboard_pan.reset()
            self._keyboard_pan_timer = 0
            return GLib.SOURCE_REMOVE
        dx, dy, active = self._keyboard_pan.step(time.monotonic())
        if dx or dy:
            width, height = self.map.get_width(), self.map.get_height()
            if width > 0 and height > 0:
                # Use Shumate's actual projection and map-source tile size.
                lat, lon = self.viewport.widget_coords_to_location(
                    self.map, width / 2 + dx, height / 2 + dy)
                self.map.center_on(lat, lon)
        if not active:
            self._keyboard_pan_timer = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _stop_keyboard_pan(self):
        self._keyboard_pan.reset()
        if self._keyboard_pan_timer:
            GLib.source_remove(self._keyboard_pan_timer)
            self._keyboard_pan_timer = 0

    def _keyboard_shortcut_pressed(self, _controller, keyval, _keycode, state):
        # Only arrow events go through the map controller. Keep all other
        # shortcuts independent (and compatible with GDK4-only environments).
        if Gdk.keyval_name(keyval) in ('Left', 'Right', 'Up', 'Down',
                                      'KP_Left', 'KP_Right', 'KP_Up', 'KP_Down'):
            if self._keyboard_pan_pressed(keyval, state):
                return True
        focused = self.get_focus()
        editing = False
        while focused is not None:
            if isinstance(focused, (Gtk.Editable, Gtk.TextView)):
                editing = True
                break
            focused = focused.get_parent()
        key = Gdk.keyval_name(keyval)
        command = keyboard_command(
            key,
            ctrl=bool(state & Gdk.ModifierType.CONTROL_MASK),
            alt=bool(state & Gdk.ModifierType.ALT_MASK),
            super_key=bool(state & Gdk.ModifierType.SUPER_MASK),
            editing=editing)
        if command is None:
            return False
        if command == 'zoom-in':
            self.zoom(1)
        elif command == 'zoom-out':
            self.zoom(-1)
        elif command == 'locate':
            self.locate()
        elif command == 'search':
            if self._dashboard_mode:
                self.set_dashboard_mode(False)
                GLib.idle_add(self.search.grab_focus)
            else:
                self.search.grab_focus()
        elif command == 'shortcuts':
            from .keyboard_shortcuts_window import show_shortcuts
            show_shortcuts(self)
        elif command in ('tower', 'sweep', 'metar', 'advisories'):
            name = {'tower': 'toggle-tower', 'sweep': 'toggle-sweep',
                    'metar': 'toggle-weather-metar',
                    'advisories': 'toggle-weather-sigmet'}[command]
            action = self.get_application().lookup_action(name)
            if action is not None and action.get_enabled():
                state_value = action.get_state()
                action.change_state(GLib.Variant.new_boolean(not state_value.get_boolean()))
        elif command == 'pip':
            self.get_application().show_pip()
        elif command in ('bookmarks', 'visible', 'emergencies'):
            if self._dashboard_mode:
                self.set_dashboard_mode(False)
            tab = {'bookmarks': 'favorites', 'visible': 'visible',
                   'emergencies': 'emergencies'}[command]
            self.show_monitor(tab)
        else:
            return False
        return True

    def _on_close_requested(self, *_args):
        self._persist_map_view()
        return self.get_application().handle_window_close()

    def _persist_map_view(self, *_args):
        """Remember the last viewport at close, not on every animation frame."""
        if getattr(self, 'viewport', None) is not None:
            try:
                save_view(self.viewport.get_latitude(), self.viewport.get_longitude(),
                          self.viewport.get_zoom_level())
            except (OSError, RuntimeError, ValueError) as exc:
                logging.getLogger('aeroscope').warning(_('Map could not be saved: %s'), exc)
        return False  # Let GTK perform the normal window close.

    def _load_style(self):
        css_file = ROOT / 'assets' / 'style.css'
        if css_file.exists():
            provider = Gtk.CssProvider()
            provider.load_from_path(str(css_file))
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def _build_ui(self):
        # Conventional GNOME hierarchy: a native header bar, a functional side
        # pane and an uncluttered map. No duplicated floating map controls.
        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        layout = Adw.ToolbarView()
        self.toast.set_child(layout)

        header = Adw.HeaderBar()
        self.window_title = Adw.WindowTitle(title='AeroScope', subtitle=_('Connecting to API…'))
        header.set_title_widget(self.window_title)
        # The geolocation shortcut already lives with +/− on the map.
        # Restore the manual radar refresh action mistakenly removed in 0.3.30.
        header.pack_end(icon_button('view-refresh-symbolic', _('Refresh aircraft'),
                                    lambda *_: self.refresh()))
        # GNOME menu sections get separators and their own descriptive labels.
        menu = Gio.Menu()
        monitoring_menu = Gio.Menu()
        append_menu_action(monitoring_menu, _('Favorite aircraft watchlist'), 'app.monitor')
        append_menu_action(monitoring_menu, _('Global emergencies'), 'app.global-alerts')
        menu.append_section(_('Monitoring'), monitoring_menu)
        visual_menu = Gio.Menu()
        append_menu_action(visual_menu, _('Control tower mode'), 'app.toggle-tower')
        append_menu_action(visual_menu, _('Rotating sweep'), 'app.toggle-sweep')
        visual_menu.append(_('Aircraft clock'), 'app.toggle-clock')
        # A string-valued stateful Gio.Action makes the menu choices mutually
        # exclusive (native radio entries). The same setting is used by the
        # preferences combo and both the main-map and mini-map markers.
        marker_menu = Gio.Menu()
        for label, mode in (
                (_('Disabled'), 'off'),
                (_('Registration (ICAO24 if unavailable)'), 'registration'),
                (_('ICAO24 only'), 'icao')):
            option = Gio.MenuItem.new(label, None)
            option.set_action_and_target_value(
                'app.marker-label', GLib.Variant.new_string(mode))
            marker_menu.append_item(option)
        visual_menu.append_submenu(_('Aircraft identification'), marker_menu)
        weather_menu = Gio.Menu()
        append_menu_action(weather_menu, _('Airport METAR · NOAA'), 'app.toggle-weather-metar')
        append_menu_action(weather_menu, _('SIGMET areas · NOAA'), 'app.toggle-weather-sigmet')
        visual_menu.append_submenu(_('Weather'), weather_menu)
        menu.append_section(_('View'), visual_menu)
        window_menu = Gio.Menu()
        append_menu_action(window_menu, _('Full screen dashboard'), 'app.toggle-dashboard')
        append_menu_action(window_menu, _('Show mini-map'), 'app.pip')
        window_menu.append(_('Hide and continue monitoring'), 'app.hide')
        menu.append_section(_('Window'), window_menu)
        application_menu = Gio.Menu()
        application_menu.append(_('Approximate IP location'), 'app.location-ip')
        append_menu_action(application_menu, _('Preferences'), 'app.preferences')
        append_menu_action(application_menu, _('Keyboard shortcuts'), 'app.shortcuts')
        application_menu.append(_('Support map providers'), 'app.support-maps')
        application_menu.append(_('About AeroScope'), 'app.about')
        append_menu_action(application_menu, _('Quit AeroScope'), 'app.quit')
        menu.append_section(_('Application'), application_menu)
        appmenu = Gtk.MenuButton(icon_name='open-menu-symbolic', tooltip_text=_('Application menu'))
        appmenu.set_menu_model(menu)
        header.pack_end(appmenu)
        layout.add_top_bar(header)
        self.main_header = header
        dashboard_keys = Gtk.EventControllerKey.new()
        dashboard_keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        dashboard_keys.connect('key-pressed', self._dashboard_escape)
        self.add_controller(dashboard_keys)
        shortcut_keys = Gtk.EventControllerKey.new()
        shortcut_keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        shortcut_keys.connect('key-pressed', self._keyboard_shortcut_pressed)
        shortcut_keys.connect('key-released', self._keyboard_pan_released)
        self.add_controller(shortcut_keys)

        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        pane.set_wide_handle(False)
        pane.set_position(345)
        pane.set_resize_start_child(False)
        # Child's natural text width must not override the user's divider.
        # The sidebar's own 318px minimum stays intact.
        pane.set_shrink_start_child(True)
        pane.set_vexpand(True)
        layout.set_content(pane)
        self.main_pane = pane

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_size_request(318, -1)
        sidebar.add_css_class('sidebar')
        self.main_sidebar = sidebar
        pane.set_start_child(sidebar)

        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        top.set_margin_top(18)
        top.set_margin_bottom(16)
        top.set_margin_start(18)
        top.set_margin_end(18)
        top.append(make_label(_('Search'), 'section-title'))
        # One unified GNOME-style search with categories in an inline section,
        # instead of a popover that could float above another application.
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search = Gtk.SearchEntry(placeholder_text=_('Flight, airport or city…'))
        self.search.set_hexpand(True)
        self.search.set_tooltip_text(_('Aircraft, airport and city suggestions. Use ↑ ↓ and Enter.'))
        self.search.connect('activate', self.on_search)
        self.search.connect('search-changed', self._search_changed)
        keys = Gtk.EventControllerKey.new()
        keys.connect('key-pressed', self._search_key_pressed)
        self.search.add_controller(keys)
        search_row.append(self.search)
        search_btn = icon_button('system-search-symbolic', _('Search'), self.on_search)
        search_btn.add_css_class('suggested-action')
        search_row.append(search_btn)
        top.append(search_row)

        # Inline results, not Gtk.Popover: a nonmodal popover creates its own
        # native surface and can remain above OTHER apps on some compositors.
        # This revealer is always part of the AeroScope sidebar and cannot leak
        # onto the desktop or detach from its owning window.
        self.suggestions_revealer = Gtk.Revealer()
        self.suggestions_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.suggestions_revealer.set_transition_duration(160)
        self.suggestions_revealer.set_reveal_child(False)
        suggest_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        suggest_frame.add_css_class('search-suggestions-inline')
        suggest_scroll = Gtk.ScrolledWindow()
        suggest_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        suggest_scroll.set_max_content_height(260)
        suggest_scroll.set_propagate_natural_height(True)
        self.suggest_listbox = Gtk.ListBox()
        self.suggest_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.suggest_listbox.set_activate_on_single_click(True)
        self.suggest_listbox.add_css_class('navigation-sidebar')
        self.suggest_listbox.connect('row-activated', self._suggestion_activated)
        suggest_scroll.set_child(self.suggest_listbox)
        suggest_frame.append(suggest_scroll)
        self.suggestions_revealer.set_child(suggest_frame)
        top.append(self.suggestions_revealer)

        self.coverage_label = make_label(_('Automatic coverage of visible area'), 'dim-label')
        # Coverage/center remain as model labels for status updates, but no
        # longer consume precious vertical room above the aircraft list.
        self.location_label = make_label(self.center_name, 'dim-label', wrap=True)
        sidebar.append(top)
        sidebar.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Details and list share vertical room, as in a GNOME inspector.
        self.sidebar_pane = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar_pane.set_vexpand(True)
        self.sidebar_pane.set_position(450)
        self.sidebar_pane.set_resize_start_child(True)
        self.sidebar_pane.set_shrink_start_child(False)
        sidebar.append(self.sidebar_pane)
        # Three native in-window tabs; no detached monitor window.
        list_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.sidebar_stack = Gtk.Stack()
        self.sidebar_stack.set_hhomogeneous(False)
        self.sidebar_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.sidebar_stack.set_transition_duration(150)
        self.sidebar_stack.set_vexpand(True)
        tabs = Gtk.StackSwitcher(stack=self.sidebar_stack)
        tabs.add_css_class('sidebar-tabs')
        self.sidebar_tabs = tabs
        tabs.set_halign(Gtk.Align.FILL)
        tabs.set_hexpand(True)
        tabs.set_margin_top(10)
        tabs.set_margin_bottom(8)
        tabs.set_margin_start(10)
        tabs.set_margin_end(10)
        list_area.append(tabs)
        list_area.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        visible_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        # The tab itself owns the count; a second heading wastes map/list space.
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class('plane-list')
        listscroll = Gtk.ScrolledWindow(vexpand=True)
        listscroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        listscroll.set_min_content_height(95)
        listscroll.set_child(self.listbox)
        listscroll.set_margin_top(4)
        visible_page.append(listscroll)
        self.visible_stack_page = self.sidebar_stack.add_titled(visible_page, 'visible', _('Visible (0)'))
        self.monitor_panel = SidebarMonitor(self, self.sidebar_stack)
        self.sidebar_stack.set_visible_child_name('visible')
        list_area.append(self.sidebar_stack)
        self.sidebar_pane.set_start_child(list_area)

        self.detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.detail_box.set_margin_start(18)
        self.detail_box.set_margin_end(18)
        self.detail_box.set_margin_top(12)
        self.detail_box.set_margin_bottom(14)
        self.detail_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.detail_scroll.set_min_content_height(140)
        self.detail_scroll.set_child(self.detail_box)
        self.sidebar_pane.set_end_child(self.detail_scroll)
        self._render_details()

        # SimpleMap ships its own zoom buttons, compass, scale and attribution;
        # GTK overlays at the same corner caused the original visual collision.
        self.simple_map = Shumate.SimpleMap.new()
        # Identify ourselves to tile servers; tiles are not unlimited free resources.
        if hasattr(Shumate, 'set_user_agent'):
            Shumate.set_user_agent(f'AeroScope/{VERSION} (+{GITHUB})')
        self.map_sources = self._create_map_sources()
        self.simple_map.set_map_source(self.map_sources[self.settings['map']])
        # Shared compact controls on the map: avoid Libshumate double controls.
        self.simple_map.set_show_zoom_buttons(False)
        self.map = self.simple_map.get_map()
        # Let the map receive keyboard focus instead of leaving SearchEntry
        # permanently focused, while retaining click-to-search behavior.
        self.map.set_focusable(True)
        # Libshumate animates both mouse-wheel and native zoom_in/out changes.
        if hasattr(self.map, 'set_animate_zoom'):
            self.map.set_animate_zoom(True)
        self.viewport = self.simple_map.get_viewport()
        lock_north_up(self.viewport, self.map, Gtk)
        self.viewport.set_zoom_level(
            self._restored_map_view[2] if self._restored_map_view else 8)
        self.map.center_on(*self.center)
        for property_name in ('latitude', 'longitude', 'zoom-level'):
            self.viewport.connect(f'notify::{property_name}', self._viewport_changed)
        self.map_overlay = Gtk.Overlay()
        self.map_overlay.set_child(self.simple_map)
        self.map_overlay.set_hexpand(True)
        self.map_overlay.set_vexpand(True)
        map_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        map_controls.set_halign(Gtk.Align.END)
        map_controls.set_valign(Gtk.Align.START)
        map_controls.set_margin_top(8)
        map_controls.set_margin_end(8)
        map_controls.add_css_class('mainmap-zoom-group')
        for icon, delta, tooltip in (
            ('list-add-symbolic', 1, _('Zoom in')),
            ('list-remove-symbolic', -1, _('Zoom out')),
        ):
            b = icon_button(icon, tooltip, lambda _button, d=delta: self.zoom(d))
            b.add_css_class('mainmap-zoom-button')
            map_controls.append(b)
        geo = icon_button('find-location-symbolic',
                          _('Center using location (GeoClue)'),
                          lambda *_: self.locate())
        geo.add_css_class('mainmap-zoom-button')
        map_controls.append(geo)
        self.radar_decoration = Gtk.DrawingArea()
        self.radar_decoration.set_can_target(False)
        self.radar_decoration.set_draw_func(self._draw_radar)
        self.radar_decoration.set_visible(self.settings['tower'])
        self.map_overlay.add_overlay(self.radar_decoration)
        self.clock_decoration = Gtk.DrawingArea()
        self.clock_decoration.set_can_target(False)
        self.clock_decoration.set_draw_func(self._draw_clock_overlay)
        self.clock_decoration.set_visible(self.settings['clock_ring'])
        self.map_overlay.add_overlay(self.clock_decoration)
        # Keep interactive map controls above transparent radar/clock layers.
        self.map_overlay.add_overlay(map_controls)
        self.exit_dashboard_button = icon_button(
            'view-restore-symbolic', _('Exit full screen (F11 or Esc)'),
            lambda *_args: self.set_dashboard_mode(False))
        self.exit_dashboard_button.add_css_class('dashboard-exit-button')
        self.exit_dashboard_button.set_halign(Gtk.Align.START)
        self.exit_dashboard_button.set_valign(Gtk.Align.START)
        self.exit_dashboard_button.set_margin_top(10)
        self.exit_dashboard_button.set_margin_start(10)
        self.exit_dashboard_button.set_visible(False)
        self.map_overlay.add_overlay(self.exit_dashboard_button)
        # Tap on empty cartographic space to dismiss the selected aircraft or
        # airport. CAPTURE observes pointer events without claiming them away
        # from libshumate's pan/zoom and marker buttons.
        self._map_press_position = None
        self.map_click = Gtk.GestureClick.new()
        self.map_click.set_button(1)
        self.map_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.map_click.connect('pressed', self._map_click_pressed)
        self.map_click.connect('released', self._map_click_released)
        self.map_click.connect('cancel', self._map_click_cancelled)
        self.map_overlay.add_controller(self.map_click)
        self._build_replay_controls()
        pane.set_end_child(self.map_overlay)
        self.trail_layer = Shumate.PathLayer.new(self.viewport)
        stroke = Gdk.RGBA()
        stroke.parse('#238fba')
        self.trail_layer.set_stroke_color(stroke)
        self.trail_layer.set_stroke_width(2.8)
        self.trail_layer.set_fill(False)
        self.simple_map.add_overlay_layer(self.trail_layer)
        # Geographic reference only: dashed route, behind aircraft markers.
        # Kept separate from the real live trail and ADSB.aero archives.
        self.route_layers = []
        route_color = Gdk.RGBA()
        route_color.parse('#b66b18')
        for _segment_index in range(3):  # at most 2 segments around the date line; spare for safety
            route_layer = Shumate.PathLayer.new(self.viewport)
            route_layer.set_stroke_color(route_color)
            route_layer.set_stroke_width(2.4)
            route_layer.set_fill(False)
            try:
                route_layer.set_dash([8, 7])
            except (AttributeError, TypeError, ValueError):
                # Older libshumate versions still display the line with a
                # different color and a clear 'estimada' label.
                pass
            self.simple_map.add_overlay_layer(route_layer)
            self.route_layers.append(route_layer)
        self.route_airport_layer = Shumate.MarkerLayer.new(self.viewport)
        self.simple_map.add_overlay_layer(self.route_airport_layer)
        self.marker_layer = Shumate.MarkerLayer.new(self.viewport)
        self.simple_map.add_overlay_layer(self.marker_layer)
        from .weather_ui import WeatherManager
        self.weather = WeatherManager(self)
        self.weather.attach(self.simple_map, self.map_overlay, self.marker_layer)
        self.airport_layer = Shumate.MarkerLayer.new(self.viewport)
        self.simple_map.add_overlay_layer(self.airport_layer)
        self.my_location_layer = Shumate.MarkerLayer.new(self.viewport)
        self.simple_map.add_overlay_layer(self.my_location_layer)
        self.replay_marker_layer = Shumate.MarkerLayer.new(self.viewport)
        self.simple_map.add_overlay_layer(self.replay_marker_layer)
        self.replay_marker = None
        self._rebuild_airports()
        # Floating panels live above the map and remain independent of the
        # sidebar, favorite slots, and geographic map coordinates.
        self.dashboard = DashboardController(self, self.map_overlay)

        # No bottom toolbar: the map uses all available height. Status is
        # exposed through the native Adw.WindowTitle subtitle in the header.
        if self.demo:
            self.set_status(_('Demo · simulated positions'))

    def _build_replay_controls(self):
        """Compact GNOME player with an optional expandable telemetry graph."""
        self.replay_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.replay_panel.set_halign(Gtk.Align.FILL)
        self.replay_panel.set_valign(Gtk.Align.END)
        for edge in ('start', 'end', 'bottom'):
            getattr(self.replay_panel, f'set_margin_{edge}')(12)
        self.replay_panel.add_css_class('replay-panel')
        self.replay_panel.set_visible(False)

        # Aircraft identity occupies the former empty header area.
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        airplane = Gtk.Image.new_from_icon_name('airplane-mode-symbolic')
        airplane.add_css_class('replay-icon-accent')
        header.append(airplane)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        names.set_hexpand(True)
        self.replay_title = make_label(_('Archived flight'), 'aircraft-name')
        self.replay_subtitle = make_label(_('ADSB.aero · flight history'), 'dim-label')
        self.replay_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.replay_subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        names.append(self.replay_title)
        names.append(self.replay_subtitle)
        header.append(names)
        chart_toggle = Gtk.ToggleButton()
        chart_toggle.set_icon_name('view-statistics-symbolic')
        chart_toggle.set_tooltip_text(_('Show or hide altitude and speed chart'))
        chart_toggle.connect('toggled', self._replay_chart_toggled)
        self.replay_chart_button = chart_toggle
        header.append(chart_toggle)
        head_center = icon_button('find-location-symbolic', _('Center historical aircraft on map'),
                                  self._replay_center_aircraft)
        head_center.add_css_class('flat')
        header.append(head_center)
        fit_route = icon_button('zoom-fit-best-symbolic', _('Fit entire historical trajectory'),
                                self._replay_fit_full_track)
        fit_route.add_css_class('flat')
        header.append(fit_route)
        close = icon_button('window-close-symbolic', _('Close playback and return to live radar'),
                            lambda *_: self._stop_replay_and_resume())
        close.add_css_class('flat')
        header.append(close)
        self.replay_panel.append(header)

        self.replay_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self.replay_scale.set_draw_value(False)
        self.replay_scale.set_hexpand(True)
        self.replay_scale.set_tooltip_text(_('Drag to change the playback time'))
        self.replay_scale.connect('value-changed', self._replay_seeked)
        self.replay_panel.append(self.replay_scale)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        start = icon_button('media-skip-backward-symbolic', _('Return to start of flight'),
                            lambda *_: self._replay_seek_to('start'))
        start.add_css_class('flat')
        row.append(start)
        back = icon_button('media-seek-backward-symbolic', _('Skip back 30 seconds of flight time'),
                           lambda *_: self._replay_seek_to(-30))
        back.add_css_class('flat')
        row.append(back)
        self.replay_play_button = icon_button('media-playback-start-symbolic', 'Reproduzir/pausar',
                                              self._replay_toggle)
        self.replay_play_button.add_css_class('suggested-action')
        row.append(self.replay_play_button)
        forward = icon_button('media-seek-forward-symbolic', _('Skip forward 30 seconds of flight time'),
                              lambda *_: self._replay_seek_to(30))
        forward.add_css_class('flat')
        row.append(forward)
        self.replay_clock = make_label('00:00:00 UTC', 'numeric')
        self.replay_clock.set_hexpand(True)
        row.append(self.replay_clock)
        row.append(make_label(_('Speed'), 'dim-label'))
        self.replay_speed = Gtk.DropDown.new_from_strings(['1×', '2×', '4×', '8×'])
        self.replay_speed.set_tooltip_text(_('Flight time multiplier'))
        self.replay_speed.connect('notify::selected', self._replay_speed_changed)
        row.append(self.replay_speed)
        self.replay_hide_live = Gtk.CheckButton(label=_('Hide live aircraft'))
        self.replay_hide_live.set_tooltip_text(_('Hide only current aircraft markers'))
        self.replay_hide_live.connect('toggled', self._replay_hide_changed)
        row.append(self.replay_hide_live)
        self.replay_panel.append(row)

        self.replay_metrics = make_label(_('Altitude —   ·   Speed —   ·   Observed distance —'), 'dim-label')
        self.replay_panel.append(self.replay_metrics)
        self.replay_quality = make_label('', 'footnote', True)
        self.replay_quality.set_visible(False)
        self.replay_panel.append(self.replay_quality)

        # Embedded GTK4/Cairo line chart. Hidden by default to preserve map area.
        self.replay_chart_revealer = Gtk.Revealer()
        self.replay_chart_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.replay_chart_revealer.set_transition_duration(200)
        graph_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        opts.append(make_label(_('Flight chart'), 'aircraft-name'))
        self.replay_altitude_toggle = Gtk.CheckButton(label=_('Altitude · blue'))
        self.replay_altitude_toggle.set_active(True)
        self.replay_altitude_toggle.connect('toggled', self._replay_chart_options_changed)
        opts.append(self.replay_altitude_toggle)
        self.replay_speed_toggle = Gtk.CheckButton(label=_('Speed · orange'))
        self.replay_speed_toggle.set_active(True)
        self.replay_speed_toggle.connect('toggled', self._replay_chart_options_changed)
        opts.append(self.replay_speed_toggle)
        opts.append(make_label(_('Horizontal axis'), 'dim-label'))
        self.replay_axis = Gtk.DropDown.new_from_strings([_('UTC time'), _('Elapsed time'), _('Distance')])
        self.replay_axis.connect('notify::selected', self._replay_chart_options_changed)
        opts.append(self.replay_axis)
        graph_area.append(opts)
        self.replay_chart = Gtk.DrawingArea()
        self.replay_chart.set_content_height(210)
        self.replay_chart.set_hexpand(True)
        self.replay_chart.set_draw_func(self._draw_replay_chart)
        self.replay_chart.add_css_class('replay-chart')
        click = Gtk.GestureClick.new()
        click.connect('pressed', self._replay_chart_pressed)
        self.replay_chart.add_controller(click)
        graph_area.append(self.replay_chart)
        self.replay_chart_revealer.set_child(graph_area)
        self.replay_panel.append(self.replay_chart_revealer)
        self.map_overlay.add_overlay(self.replay_panel)

    def _replay_chart_toggled(self, button):
        self.replay_chart_revealer.set_reveal_child(button.get_active())
        self._replay_chart_last_draw = 0.0
        if button.get_active():
            self.replay_chart.queue_draw()

    def _replay_chart_options_changed(self, *_):
        self._replay_chart_last_draw = 0.0
        self.replay_chart.queue_draw()

    def _replay_chart_axis(self):
        return ('clock', 'elapsed', 'distance')[min(2, self.replay_axis.get_selected())]

    def _draw_replay_chart(self, area, cr, width, height):
        if not self.replay_track:
            return
        plot_chart(self.replay_track, cr, width, height, self.replay_time,
                   axis=self._replay_chart_axis(),
                   altitude=self.replay_altitude_toggle.get_active(),
                   speed=self.replay_speed_toggle.get_active(),
                   dark=Adw.StyleManager.get_default().get_dark())

    def _replay_chart_pressed(self, gesture, n_press, x, y):
        if not self.replay_track:
            return
        ratio = chart_hit_fraction(x, self.replay_chart.get_width())
        self.replay_time = time_for_fraction(self.replay_track, ratio, self._replay_chart_axis())
        self._replay_last_tick = time.monotonic()
        self._replay_rendered_at = None
        self._render_replay_frame()

    def _replay_seek_to(self, step):
        if not self.replay_track:
            return
        target = self.replay_track.start if step == 'start' else self.replay_time + step
        self.replay_time = min(self.replay_track.end, max(self.replay_track.start, target))
        self._replay_last_tick = time.monotonic()
        self._replay_rendered_at = None
        self._render_replay_frame()

    def _replay_center_aircraft(self, *_):
        if self.replay_track and self.replay_time is not None:
            fix = self.replay_track.seek(self.replay_time)
            if fix:
                self.map.center_on(fix.lat, fix.lon)

    def _replay_fit_full_track(self, *_):
        if not self.replay_track:
            return
        fitted = fit_trajectory(self.replay_track.full_coordinates(),
                                max(360, self.map.get_width()),
                                max(320, self.map.get_height()))
        if fitted:
            lat, lon, zoom = fitted
            self.map.center_on(lat, lon)
            self.viewport.set_zoom_level(zoom)

    def _draw_replay_aircraft(self, _widget, cr, width, height):
        # Distinct violet aircraft silhouette, no road-sign badge or tile.
        cr.save()
        cr.translate((width-56)/2, (height-56)/2)
        paint_replay_aircraft(cr, self.replay_model, self.replay_heading)
        cr.restore()

    def _replay_speed_changed(self, dropdown, _pspec):
        self.replay_rate = (1, 2, 4, 8)[min(3, dropdown.get_selected())]

    def _replay_hide_changed(self, button):
        if hasattr(self, 'marker_layer'):
            self.marker_layer.set_visible(not button.get_active())

    def _replay_toggle(self, *_):
        if self.replay_track is None:
            return
        if self.replay_time is not None and self.replay_time >= self.replay_track.end:
            self.replay_time = self.replay_track.start
        self.replay_running = not self.replay_running
        self._replay_last_tick = time.monotonic()
        self.replay_play_button.set_icon_name('media-playback-pause-symbolic' if self.replay_running
                                               else 'media-playback-start-symbolic')

    def _replay_seeked(self, scale):
        if self._replay_slider_changing or not self.replay_track:
            return
        self.replay_time = self.replay_track.start + self.replay_track.duration * scale.get_value() / 1000
        self._replay_last_tick = time.monotonic()
        self._replay_rendered_at = None
        self._render_replay_frame()

    def _replay_tick(self):
        if self.replay_track is None:
            self._replay_timer_id = 0
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        if self.replay_running:
            elapsed = min(2, max(0, now - self._replay_last_tick))
            self.replay_time = min(self.replay_track.end, self.replay_time + elapsed * self.replay_rate)
            if self.replay_time >= self.replay_track.end:
                self.replay_running = False
                self.replay_play_button.set_icon_name('media-playback-start-symbolic')
            self._render_replay_frame()
        self._replay_last_tick = now
        return GLib.SOURCE_CONTINUE

    def _render_replay_frame(self):
        if self.replay_track is None or self.replay_time is None:
            return
        fix = self.replay_track.seek(self.replay_time)
        if fix is None:
            return
        if self.replay_marker is not None:
            self.replay_marker.set_location(fix.lat, fix.lon)
            self.replay_heading = self.replay_track.bearing_at(self.replay_time, self.replay_heading)
            self.replay_art.queue_draw()
        clock = datetime.datetime.fromtimestamp(self.replay_time, datetime.timezone.utc)
        self.replay_clock.set_text(clock.strftime('%d/%m · %H:%M:%S UTC'))
        km = self.replay_track.distance_at(self.replay_time)
        alt = _('{value0:,.0f} feet').format(value0=fix.altitude_ft).replace(',', '.') if fix.altitude_ft is not None else _('unavailable')
        speed = f'{fix.speed_kt*1.852:,.0f} km/h'.replace(',', '.') if fix.speed_kt is not None else _('unavailable')
        self.replay_metrics.set_text(_('Altitude {value0}   ·   Velocidade {value1}   ·   Observed distance {value2:.1f} km').format(value0=alt, value1=speed, value2=km))
        self.replay_quality.set_visible(bool(fix.coverage_gap))
        if fix.coverage_gap:
            self.replay_quality.set_text(_('No ADS-B coverage during this interval: historical position held at last recorded point.'))
        self._replay_slider_changing = True
        self.replay_scale.set_value(1000 * (self.replay_time-self.replay_track.start) /
                                    max(.001, self.replay_track.duration))
        self._replay_slider_changing = False
        # Graph lines always cover the complete archived flight; only the
        # vertical cursor moves along the chosen axis.
        if self.replay_chart_revealer.get_reveal_child():
            chart_now = time.monotonic()
            if chart_now - self._replay_chart_last_draw >= .17:
                self._replay_chart_last_draw = chart_now
                self.replay_chart.queue_draw()
        if self._replay_rendered_at is not None and abs(self.replay_time - self._replay_rendered_at) < 0.30:
            return
        self._replay_rendered_at = self.replay_time
        segments = self.replay_track.visible_segments(self.replay_time)
        for layer in self.archive_layers:
            layer.remove_all()
        for layer, points in zip(self.archive_layers, segments):
            for lat, lon in points:
                layer.add_node(Shumate.Coordinate.new_full(lat, lon))

    def _stop_replay_and_resume(self):
        self._clear_archive_layers()
        self._set_history_mode(False)
        self._next_poll_due = time.monotonic() + .3
        self.set_status(_('Live radar resumed'))
        self._render_details()

    def _search_changed(self, *_):
        query = self.search.get_text().strip()
        if self._ignore_search_text == query:
            return
        self._ignore_search_text = None
        self._search_committed = False
        self._search_generation += 1
        if self._search_timer:
            GLib.source_remove(self._search_timer)
            self._search_timer = 0
        self._search_city_error = None
        self._render_search_suggestions()
        if len(query) >= 3 and self._can_geocode_query(query):
            cache_key = normalized(query)
            if cache_key not in self._search_city_cache:
                self._search_timer = GLib.timeout_add(600, self._start_city_suggestions,
                                                      query, self._search_generation)

    @staticmethod
    def _can_geocode_query(query):
        candidate = query.strip().upper().replace(' ', '')
        # Don't spend a geocoding request on an obvious callsign, registration,
        # or ICAO24 code. Real cities can still be found by their names.
        return classify_aircraft_identifier(candidate) is None

    def _start_city_suggestions(self, query, generation):
        self._search_timer = 0
        if (generation != self._search_generation or self._search_committed
                or query != self.search.get_text().strip()):
            return GLib.SOURCE_REMOVE
        if self._city_fetch_inflight:
            # Recheck after the in-flight request completes; never parallelise
            # multiple autocomplete geocoding requests.
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        delay = 1.8 - (now - self._last_city_request)
        if delay > 0:
            self._search_timer = GLib.timeout_add(max(100, int(delay*1000)),
                                                  self._start_city_suggestions,
                                                  query, generation)
            return GLib.SOURCE_REMOVE
        self._city_fetch_inflight = True
        self._last_city_request = now
        self._async(lambda: geocode_city(query),
                    lambda rows, error: self._city_suggestions_done(query, rows, error))
        return GLib.SOURCE_REMOVE

    def _city_suggestions_done(self, query, rows, error):
        self._city_fetch_inflight = False
        key = normalized(query)
        self._search_city_cache[key] = city_suggestions(query, rows or []) if not error else []
        # Prevent unbounded growth if the app stays open and many searches occur.
        if len(self._search_city_cache) > 80:
            self._search_city_cache.pop(next(iter(self._search_city_cache)))
        current = self.search.get_text().strip()
        if (normalized(current) == key and not self._ignore_search_text
                and not self._search_committed and self.is_active()):
            self._search_city_error = str(error) if error else None
            self._render_search_suggestions()
        elif (not self._search_committed and self.is_active()
              and len(current) >= 3 and self._can_geocode_query(current)
              and normalized(current) not in self._search_city_cache
              and not self._search_timer):
            self._search_timer = GLib.timeout_add(600, self._start_city_suggestions,
                                                  current, self._search_generation)
        return GLib.SOURCE_REMOVE

    def _start_historical_search(self, query):
        kind = classify_aircraft_identifier(query)
        if not kind:
            self.notify(_('Search history by callsign, registration or ICAO24 address.'))
            return
        if self.demo:
            self.notify(_('The historical archive requires a real internet connection.'))
            return
        key = normalized(query)
        self._search_committed = False
        self._history_search_errors.pop(key, None)
        if key in self._history_search_cache:
            self._render_search_suggestions()
            return
        if key in self._history_search_pending:
            self._render_search_suggestions()
            return
        self._history_search_pending.add(key)
        self._render_search_suggestions()
        self._async(lambda: search_historical_flights(kind, query, days=30),
                    lambda rows, error: self._historical_search_done(query, rows, error))

    def _historical_search_done(self, query, rows, error):
        key = normalized(query)
        self._history_search_pending.discard(key)
        if error:
            self._history_search_errors[key] = str(error)
            logging.getLogger('aeroscope.history').warning(_('Search failed for %s: %s'), query, error)
        else:
            self._history_search_cache[key] = rows if isinstance(rows, list) else []
            for entry in self._history_search_cache[key]:
                if isinstance(entry, dict) and entry.get('flight_id'):
                    self._history_search_metadata[str(entry['flight_id'])] = entry
            if len(self._history_search_cache) > 35:
                self._history_search_cache.pop(next(iter(self._history_search_cache)))
        if normalized(self.search.get_text()) == key and self.is_active():
            self._search_committed = False
            self._render_search_suggestions()
        return GLib.SOURCE_REMOVE

    def _activate_historical_flight(self, flight_id):
        self._clear_global_selection()
        entry = self._history_search_metadata.get(flight_id)
        if not isinstance(entry, dict):
            self.notify(_('Archived flight not found in this search.'))
            return
        hexid = str(entry.get('icao24') or '').lower()
        if not re.fullmatch(r'[a-f0-9]{6}', hexid):
            self.notify(_('Historical record has no valid ICAO24 identifier.'))
            return
        self._clear_route_visual()
        self._clear_archive_layers()
        self.selected_airport = None
        self.selected_weather_station = None
        self.selected_hex = hexid
        rows = self.history_info.setdefault(hexid, [])
        if not any(item.get('flight_id') == flight_id for item in rows):
            rows.insert(0, entry)
        self.follow = False
        self._sync_marker_selection()
        self._render_details()
        self._adjust_sidebar()
        self.show_historical_track(flight_id)

    def _suggestion_heading(self, title):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        label = make_label(title, 'search-group-heading')
        label.set_margin_start(12)
        label.set_margin_end(12)
        label.set_margin_top(9)
        label.set_margin_bottom(4)
        row.set_child(label)
        self.suggest_listbox.append(row)

    def _render_search_suggestions(self):
        query = self.search.get_text().strip()
        child = self.suggest_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.suggest_listbox.remove(child)
            child = next_child
        self._suggestion_rows.clear()
        if not query or self._search_committed:
            self._hide_suggestions()
            return

        suggestions = local_suggestions(query, self.records.values(), AIRPORTS, aircraft_name)
        suggestions.extend(self._search_city_cache.get(normalized(query), []))
        key = normalized(query)
        archived = self._history_search_cache.get(key)
        if archived is not None:
            suggestions.extend(historical_suggestions(query, archived))
        elif self.settings.get('history') and classify_aircraft_identifier(query):
            suggestions.append(SearchSuggestion(
                'archive_action', query, _('Search archived flights'),
                _('ADSB.aero · up to 30 days · on demand')))
        names = {'aircraft': (_('Live aircraft'), 'airplane-mode-symbolic'),
                 'history': (_('Flight history'), 'document-open-recent-symbolic'),
                 'archive_action': (_('ADSB.aero archive'), 'system-search-symbolic'),
                 'airport': (_('Airports'), 'mark-location-symbolic'),
                 'city': (_('Cities'), 'find-location-symbolic')}
        for kind, entries in grouped_suggestions(suggestions):
            heading, icon = names[kind]
            self._suggestion_heading(heading)
            for item in entries:
                row = Gtk.ListBoxRow()
                row._aeroscope_result = item
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                box.set_margin_start(12)
                box.set_margin_end(12)
                box.set_margin_top(8)
                box.set_margin_bottom(8)
                symbol = Gtk.Image.new_from_icon_name(icon)
                symbol.set_pixel_size(18)
                symbol.add_css_class('dim-label')
                box.append(symbol)
                labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                labels.set_hexpand(True)
                name = make_label(item.title, 'search-result-title')
                name.set_ellipsize(Pango.EllipsizeMode.END)
                labels.append(name)
                desc = make_label(item.subtitle, 'dim-label')
                desc.set_ellipsize(Pango.EllipsizeMode.END)
                labels.append(desc)
                box.append(labels)
                row.set_child(box)
                self.suggest_listbox.append(row)
                self._suggestion_rows.append(row)

        # A live geocoding search is not part of the ADSB.lol request budget.
        city_coming = (len(query) >= 3 and self._can_geocode_query(query)
                       and normalized(query) not in self._search_city_cache)
        if city_coming and not any(item.kind == 'city' for item in suggestions):
            self._suggestion_heading(_('Cities'))
            self._suggestion_notice(_('Searching cities…'))
        if key in self._history_search_pending:
            self._suggestion_heading(_('Flight history'))
            self._suggestion_notice(_('Checking archived records…'))
        elif key in self._history_search_errors:
            self._suggestion_heading(_('Flight history'))
            self._suggestion_notice(_('History request failed: ') + self._history_search_errors[key][:90])
        elif archived is not None and not archived:
            self._suggestion_heading(_('Flight history'))
            self._suggestion_notice(_('No records in the recently checked pages (up to 30 days).'))
        if not suggestions and not city_coming and key not in self._history_search_pending and archived is None:
            self._suggestion_notice(_('No local suggestions. Press Enter to search.'))
        if suggestions or len(query) >= 2:
            self._show_suggestions()
        else:
            self._hide_suggestions()

    def _show_suggestions(self):
        self.suggestions_revealer.set_reveal_child(True)

    def _hide_suggestions(self):
        self.suggestions_revealer.set_reveal_child(False)

    def _suggestions_visible(self):
        return self.suggestions_revealer.get_reveal_child()

    def _window_activity_changed(self, _window, _pspec):
        if not self.is_active() and self._suggestions_visible():
            # Even a late geocoding callback must not bring the results back
            # after another app takes focus.
            self._commit_search()

    def _commit_search(self):
        self._search_committed = True
        self._search_generation += 1
        if self._search_timer:
            GLib.source_remove(self._search_timer)
            self._search_timer = 0
        self._hide_suggestions()

    def _suggestion_notice(self, message):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        label = make_label(message, 'dim-label', True)
        for margin in ('start', 'end', 'top', 'bottom'):
            getattr(label, f'set_margin_{margin}')(10)
        row.set_child(label)
        self.suggest_listbox.append(row)

    def _suggestion_activated(self, _box, row):
        suggestion = getattr(row, '_aeroscope_result', None)
        if suggestion is not None:
            self._activate_suggestion(suggestion)

    def _activate_suggestion(self, result):
        if result.kind == 'archive_action':
            self._start_historical_search(result.key)
            return
        self._commit_search()
        if result.kind == 'history':
            # Keep original query in the field, so archived results are still
            # available after closing the player or editing the search.
            self._activate_historical_flight(result.key)
            return
        self._ignore_search_text = result.title
        self.search.set_text(result.title)
        if result.kind == 'aircraft':
            self.select_plane(result.key)
        elif result.kind == 'airport':
            self.move_to(result.lat, result.lon, result.title, 10)
            self.select_airport(result.key)
        elif result.kind == 'city':
            self.move_to(result.lat, result.lon,
                         f'{result.title}, {result.subtitle}', 9)

    def _search_key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            if self._suggestions_visible():
                self._commit_search()
                return True
            return False
        if keyval not in (Gdk.KEY_Down, Gdk.KEY_Up, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        if not self._suggestions_visible():
            if keyval in (Gdk.KEY_Down, Gdk.KEY_Up) and self.search.get_text().strip():
                self._render_search_suggestions()
            else:
                return False
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = self.suggest_listbox.get_selected_row()
            if selected is not None and getattr(selected, '_aeroscope_result', None) is not None:
                self._suggestion_activated(self.suggest_listbox, selected)
                return True
            return False
        if not self._suggestion_rows:
            return False
        selected = self.suggest_listbox.get_selected_row()
        try:
            index = self._suggestion_rows.index(selected)
        except ValueError:
            index = -1 if keyval == Gdk.KEY_Down else 0
        index = (index + (1 if keyval == Gdk.KEY_Down else -1)) % len(self._suggestion_rows)
        self.suggest_listbox.select_row(self._suggestion_rows[index])
        return True

    def _create_map_sources(self):
        registry = Shumate.MapSourceRegistry.new_with_defaults()
        osm = registry.get_by_id(Shumate.MAP_SOURCE_OSM_MAPNIK)
        if osm is None:
            osm = Shumate.RasterRenderer.new_full_from_url(
                'osm', 'OpenStreetMap', '© OpenStreetMap contributors',
                'https://www.openstreetmap.org/copyright', 0, 19, 256,
                Shumate.MapProjection.MERCATOR,
                'https://tile.openstreetmap.org/{z}/{x}/{y}.png')
        topographic = Shumate.RasterRenderer.new_full_from_url(
            'topo', 'OpenTopoMap-R · openmaps.fr',
            '© OpenTopoMap-R, © OpenStreetMap · Apoie openmaps.fr',
            'https://openmaps.fr/tile-usage-policy.html', 0, 16, 256,
            Shumate.MapProjection.MERCATOR,
            'https://tile.openmaps.fr/opentopomap/{z}/{x}/{y}.png')
        hiking = Shumate.RasterRenderer.new_full_from_url(
            'hiking', 'OpenHikingMap · openmaps.fr',
            '© OpenHikingMap, © OpenStreetMap · Apoie openmaps.fr',
            'https://openmaps.fr/tile-usage-policy.html', 0, 16, 256,
            Shumate.MapProjection.MERCATOR,
            'https://tile.openmaps.fr/openhikingmap/{z}/{x}/{y}.png')
        return {'osm': osm, 'topo': topographic, 'hiking': hiking}

    def _apply_theme(self):
        scheme = {'system': Adw.ColorScheme.DEFAULT,
                  'light': Adw.ColorScheme.FORCE_LIGHT,
                  'dark': Adw.ColorScheme.FORCE_DARK}[self.settings['theme']]
        Adw.StyleManager.get_default().set_color_scheme(scheme)

    def _tower_sweep_enabled(self):
        return bool(self.settings.get('tower') and self.settings.get('tower_sweep', False))

    def _tower_sweep_angle(self, now=None):
        if now is None:
            now = time.monotonic()
        # One revolution per regular radar interval; this is display-only.
        duration = max(10.0, float(self.poll_seconds))
        return ((now - self._sweep_start_at) / duration * 360.0) % 360.0

    def _update_tower_sweep_timer(self):
        if self._tower_sweep_enabled() and not self._sweep_source:
            now = time.monotonic()
            # Moving sprites must STOP as soon as scan mode is enabled.
            # Continue tracking received fixes internally; only the beam
            # is allowed to release a new screen position.
            for marker in self.markers.values():
                if marker.transition is not None:
                    marker.animation_step(now)
                    marker.transition = None
            self._sweep_start_at = now
            self._sweep_last_tick_at = now
            self._sweep_previous_tick_at = now
            self._sweep_previous_angle = 0.0
            self._sweep_source = GLib.timeout_add(50, self._tower_sweep_tick)
        elif not self._tower_sweep_enabled():
            if self._sweep_source:
                GLib.source_remove(self._sweep_source)
                self._sweep_source = 0
            self._resume_live_positions_after_sweep()

    def _sweep_point_bearing(self, lat, lon):
        """Bearing of a virtual fix on this viewport, not the held sprite."""
        try:
            x, y = self.viewport.location_to_widget_coords(self.map, lat, lon)
            width, height = self.map.get_width(), self.map.get_height()
            if width <= 0 or height <= 0 or not (0 <= x <= width and 0 <= y <= height):
                return None
            return bearing_on_screen(x - width / 2, y - height / 2)
        except (TypeError, ValueError, AttributeError):
            return None

    def _sweep_marker_bearing(self, marker):
        # Kept for viewport helpers, but never used to trigger a scan release.
        return self._sweep_point_bearing(marker.marker.get_latitude(),
                                         marker.marker.get_longitude())

    def _release_sweep_position(self, hexid, *, force_latest=False):
        pending = self._sweep_pending.pop(hexid, None)
        marker = self.markers.get(hexid)
        if not pending or marker is None:
            return
        plane, bearing = pending
        now = time.monotonic()
        virtual = self._sweep_virtual.get(hexid)
        # The interpolated position exists internally even while the icon is
        # frozen. Only the beam crossing makes this point visible. Never
        # extrapolate beyond the last ADS-B fix.
        target = ((plane.lat, plane.lon) if force_latest or virtual is None else
                  virtual.sample(now)[0])
        start = (marker.marker.get_latitude(), marker.marker.get_longitude())
        marker.transition = None
        marker.plane = plane
        marker.bearing = bearing
        if self.settings['animate_aircraft'] and distance_nm(*start, *target) > .015:
            # The short visual glide is only initiated once the beam has
            # intersected the internally interpolated current position.
            # A bounded glide avoids the conspicuous artificial dash that
            # occurred when 10-60 seconds of travel were squeezed into 380ms.
            separation = distance_nm(*start, *target)
            glide = min(1.5, max(0.55, .55 + separation * .16))
            marker.transition = PositionTransition(start, target, now, glide)
        else:
            marker.marker.set_location(*target)
        marker.last_fix_at = now
        marker.area.queue_draw()
        if self.settings['tower']:
            self.radar_decoration.queue_draw()
        self._start_animation_timer()

    def _release_all_sweep_positions(self):
        for hexid in tuple(self._sweep_pending):
            self._release_sweep_position(hexid, force_latest=True)
        self._sweep_virtual.clear()

    def _resume_live_positions_after_sweep(self):
        """Continue smooth normal playback immediately from the last drawn fix.

        A cached virtual track contains the last confirmed ADS-B target and
        its projected *on-screen interpolation time*, even if the beam had not
        reached the sprite. We hand that target to the regular animation timer
        without making a fresh API call. Sprites already visited by the beam
        are covered too, not merely the ones still in `_sweep_pending`.
        """
        now = time.monotonic()
        for hexid, virtual in tuple(self._sweep_virtual.items()):
            marker = self.markers.get(hexid)
            if marker is None:
                continue
            pending = self._sweep_pending.get(hexid)
            latest = pending[0] if pending else self.records.get(hexid)
            if latest is None:
                continue
            bearing = pending[1] if pending else self.bearings.get(hexid, latest.track)
            start = (marker.marker.get_latitude(), marker.marker.get_longitude())
            target = virtual.end
            marker.plane = latest
            marker.bearing = bearing
            # The movement in memory already has its own timescale. Preserve
            # the remaining duration instead of a 0.38s rush to the endpoint.
            remaining = max(0.35, virtual.duration - (now - virtual.started_at))
            marker.transition = None
            if (self.settings['animate_aircraft'] and
                    distance_nm(*start, *target) > .015):
                marker.transition = PositionTransition(start, target, now, remaining)
            else:
                marker.marker.set_location(*target)
            marker.last_fix_at = now
            marker.area.queue_draw()
        # Safety net for any buffered record without an active interpolation.
        for hexid in tuple(self._sweep_pending):
            if hexid not in self._sweep_virtual:
                self._release_sweep_position(hexid, force_latest=True)
        self._sweep_pending.clear()
        self._sweep_virtual.clear()
        self._start_animation_timer()

    def _tower_sweep_tick(self):
        if not self._tower_sweep_enabled():
            self._sweep_source = 0
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        angle = self._tower_sweep_angle(now)
        previous = self._sweep_previous_angle
        cycle = max(10.0, float(self.poll_seconds))
        # If the GUI suspended for a full revolution, release all buffered fixes.
        full_turn = now - getattr(self, '_sweep_last_tick_at', now) >= cycle
        self._sweep_last_tick_at = now
        previous_time = getattr(self, '_sweep_previous_tick_at', now)
        for hexid in tuple(self._sweep_pending):
            marker = self.markers.get(hexid)
            virtual = self._sweep_virtual.get(hexid)
            if marker is None:
                self._sweep_pending.pop(hexid, None)
                self._sweep_virtual.pop(hexid, None)
                continue
            if virtual is None:
                continue
            # Sample the internal motion at both ends of this *same* sweep
            # frame. Never test against marker.marker: that is intentionally
            # frozen until a beam intersects the virtual aircraft position.
            before, _ = virtual.sample(previous_time)
            current, _ = virtual.sample(now)
            bearing_before = self._sweep_point_bearing(*before)
            bearing_current = self._sweep_point_bearing(*current)
            if (bearing_before is not None and bearing_current is not None and
                    crossed_moving_target(previous, angle, bearing_before,
                                          bearing_current, full_turn=full_turn)):
                self._release_sweep_position(hexid)
        self._sweep_previous_tick_at = now
        self._sweep_previous_angle = angle
        self.radar_decoration.queue_draw()
        # Repaint the PiP's scan at the same angle, without a separate timer.
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None:
            pip.redraw_tower_sweep()
        return GLib.SOURCE_CONTINUE

    def _tower_ring_distance_nm(self, cx, cy, pixel_radius):
        """Web Mercator scale available on the first drawn frame.

        Gtk allocations and widget-to-location conversions can be invalid
        during startup. Computing from zoom/latitude avoids labels silently
        disappearing until a later redraw.
        """
        zoom = self.viewport.get_zoom_level()
        lat = self.viewport.get_latitude()
        return pixel_radius * meters_per_pixel(lat, zoom) / 1852.0

    def _selected_tower_reference(self, width, height):
        """The clock is relative to the selected *displayed* aircraft."""
        marker = self.markers.get(self.selected_hex) if self.selected_hex else None
        if marker is None:
            return None
        try:
            x, y = self.viewport.location_to_widget_coords(
                self.map, marker.marker.get_latitude(), marker.marker.get_longitude())
            heading = float(marker.bearing)
            if not all(map(math.isfinite, (x, y, heading))):
                return None
            if not (0 <= x <= width and 0 <= y <= height):
                return None
            return x, y, heading % 360
        except (ValueError, AttributeError, TypeError):
            return None

    def _draw_relative_clock(self, cr, width, height):
        """12-o'clock is the selected aircraft's nose, not the map's north.

        Clock geometry uses the selected marker's *visible* location. Its
        direction is the same screen rotation used to paint the silhouette.
        """
        reference = self._selected_tower_reference(width, height)
        if reference is None:
            return
        cx, cy, heading = reference
        radius = clock_ring_radius(width, height, cx, cy)
        if radius < 48:
            return
        # Two-layer outline: dark contrast beneath a bright mint edge. A
        # single pale stroke disappeared on OpenStreetMap's light background.
        cr.set_line_width(4.0)
        cr.set_source_rgba(.03, .12, .16, .76)
        cr.arc(cx, cy, radius, 0, math.tau)
        cr.stroke()
        cr.set_line_width(1.75)
        cr.set_source_rgba(.73, 1, .88, .96)
        cr.arc(cx, cy, radius, 0, math.tau)
        cr.stroke()
        # Stronger line at 12/0 points exactly along the aircraft's nose.
        cr.set_source_rgba(1, .86, .40, .82)
        head = math.radians(heading)
        cr.move_to(cx + math.sin(head)*max(12, radius-29),
                   cy - math.cos(head)*max(12, radius-29))
        cr.line_to(cx + math.sin(head)*radius, cy-math.cos(head)*radius)
        cr.stroke()
        cr.select_font_face('Sans', 0, 1)
        cr.set_font_size(11)
        for hour, angle in enumerate(clock_hour_bearings(heading)):
            rad = math.radians(angle)
            x = cx + math.sin(rad)*radius
            y = cy - math.cos(rad)*radius
            label = '12/0' if hour == 0 else str(hour)
            ext = cr.text_extents(label)
            text_width = ext.width if hasattr(ext, 'width') else ext[2]
            box_width = max(22, text_width+12)
            left = x - box_width / 2
            top = y - 11
            # The aircraft clock is fixed around its icon. Do not drag the
            # hour labels to screen borders: they belong to the fixed circle.
            # Cairo naturally clips the portion outside the map viewport.
            cr.set_source_rgba(.04, .12, .15, .88)
            cr.rectangle(left, top, box_width, 21)
            cr.fill()
            if hour == 0:
                cr.set_source_rgba(1, .85, .35, 1)
            elif hour in (3, 6, 9):
                cr.set_source_rgba(.96, .99, 1, 1)
            else:
                cr.set_source_rgba(.75, .93, .88, .95)
            cr.move_to(left+(box_width-text_width)/2, top+14.7)
            cr.show_text(label)

    def _draw_clock_overlay(self, _widget, cr, width, height):
        if self.settings['clock_ring'] and self.selected_hex is not None:
            self._draw_relative_clock(cr, width, height)

    def _draw_radar(self, _widget, cr, width, height):
        """Tower circles cover all map corners; clock is aircraft-relative."""
        if not self.settings['tower'] or width < 100 or height < 100:
            return
        cr.set_source_rgba(0.0, .07, .09, .32)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cx, cy = width / 2, height / 2
        # A circle based on min(width,height) misses wide-screen corners.
        # The outer radius must reach the farthest corner of the map rectangle.
        radius = full_map_radius(width, height, cx, cy)
        cr.set_line_width(1.0)
        # The sweep reaches the corners, but that outermost circumference
        # touches the map only at the corners. Keep distance rings within the
        # useful area so their labels really sit on the visible circles.
        visible_ring_radius = radius * .88
        for part in (.25, .50, .75, 1.0):
            r = visible_ring_radius * part
            cr.set_source_rgba(.35, 1, .68, .36)
            # Cairo arc() implicitly joins the previous current point to the
            # start of the circle. show_text() leaves that point at the end
            # of the preceding label: without new_path(), a stray diagonal
            # connects each distance label to the next circle.
            cr.new_path()
            cr.arc(cx, cy, r, 0, math.tau)
            cr.stroke()
            distance = self._tower_ring_distance_nm(cx, cy, r)
            if not (distance > 0 and math.isfinite(distance)):
                continue
            label = ring_label(distance, self.settings['speed'])
            cr.select_font_face('Sans', 0, 0)
            cr.set_font_size(11)
            ext = cr.text_extents(label)
            text_width = ext.width if hasattr(ext, 'width') else ext[2]
            box_width = text_width + 12
            anchor = ring_label_anchor(cx, cy, r, width, height, box_width)
            if anchor is None:
                continue
            x, y = anchor
            cr.set_source_rgba(0, .06, .08, .83)
            cr.rectangle(x, y, box_width, 18)
            cr.fill()
            cr.set_source_rgba(.64, 1, .80, .94)
            cr.move_to(x + 6, y+13)
            cr.show_text(label)
            cr.new_path()  # Text must not join the next radar circle.
        # No radial spokes: they crossed the distance labels and looked like
        # leader lines. Only the concentric circles and optional sweep remain.
        if self._tower_sweep_enabled():
            heading = math.radians(self._tower_sweep_angle())
            for trail in range(11, -1, -1):
                angle = heading - trail * math.radians(2.0)
                cr.set_source_rgba(.30, 1, .56, .065 + .47*(1-trail/12)**2)
                cr.set_line_width(1.25 + (1-trail/12)*1.3)
                cr.move_to(cx, cy)
                cr.line_to(cx + math.sin(angle)*radius, cy - math.cos(angle)*radius)
                cr.stroke()

    def show_preferences(self):
        if getattr(self, '_preferences_window', None) is not None:
            self._preferences_window.present()
            return
        dialog = PreferencesWindow(self, self.settings, self._change_setting,
                                   self._clear_app_cache, self._clear_all_trails,
                                   self.confirm_ip_location)
        dialog.connect('close-request', self._prefs_closed)
        self._preferences_window = dialog
        dialog.present()

    def _prefs_closed(self, *_):
        self._preferences_window = None
        return False

    def _change_setting(self, key, value):
        if key not in self.settings or self.settings[key] == value:
            return
        if key == 'autostart_login':
            try:
                configure_autostart(bool(value))
            except OSError as exc:
                logging.getLogger('aeroscope.autostart').warning('Autostart: %s', exc)
                dialog = Adw.MessageDialog.new(self, _('Could not configure startup at login'), str(exc))
                dialog.add_response('ok', 'OK')
                dialog.present()
                self.settings[key] = not bool(value)
                save(self.settings)
                prefs = getattr(self, '_preferences_window', None)
                if prefs is not None:
                    prefs.sync_background_setting(key, self.settings[key])
                return
        self.settings[key] = value
        save(self.settings)
        self.get_application().sync_visual_action(key, value)
        prefs = getattr(self, '_preferences_window', None)
        if prefs is not None and key in ('tower', 'clock_ring', 'tower_sweep', 'marker_label'):
            prefs.sync_visual_setting(key, value)
        if prefs is not None and (key.startswith('weather_') or key in ('sigmet_fill', 'sigmet_colors')):
            prefs.sync_weather_setting(key, value)
        if key.startswith('weather_'):
            self.weather.settings_changed()
        elif key in ('sigmet_fill', 'sigmet_colors'):
            # Visual-only preferences never invalidate the 15-minute NOAA
            # schedule or make fresh network requests.
            self.weather.presentation_changed(key)
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None and key in (
                'map', 'tower', 'tower_sweep', 'clock_ring', 'show_airports',
                'weather_metar', 'weather_sigmet', 'sigmet_fill', 'sigmet_colors',
                'altitude_perspective', 'marker_label', 'speed', 'enable_hover'):
            pip.sync_visuals()
            if pip.get_visible() and key in ('altitude_perspective', 'marker_label',
                                              'speed', 'enable_hover'):
                pip.sync_aircraft()
        if key == 'theme':
            self._apply_theme()
        elif key == 'map':
            self.simple_map.set_map_source(self.map_sources[value])
            self.radar_decoration.queue_draw()
            # Different providers may use different tile sizes, changing the
            # SIGMET Mercator pixel scale without a zoom-level notification.
            for weather_view in self.weather.views:
                weather_view.sigmet_canvas.queue_draw()
        elif key == 'tower':
            self.radar_decoration.set_visible(value)
            self._update_tower_sweep_timer()
            self.radar_decoration.queue_draw()
        elif key == 'tower_sweep':
            self._update_tower_sweep_timer()
            self.radar_decoration.queue_draw()
        elif key == 'clock_ring':
            self.clock_decoration.set_visible(value)
            self.clock_decoration.queue_draw()
        elif key == 'show_airports':
            self._rebuild_airports()
        elif key in ('refresh', 'refresh_background'):
            # The timer detects map/PiP/tray mode and changes the active
            # cadence without restarting favorite/emergency monitoring.
            self._regional_mode = None
            self._sync_regional_cadence()
        elif key == 'animate_aircraft':
            if not value:
                for marker in self.markers.values():
                    if self._tower_sweep_enabled():
                        marker.transition = None  # leave the displayed fix frozen
                    else:
                        marker.stop_animation()
                if self._animation_source:
                    GLib.source_remove(self._animation_source)
                    self._animation_source = 0
                if self.follow and self.selected_hex in self.markers:
                    p = self.markers[self.selected_hex].marker
                    self._center_on_animation(p.get_latitude(), p.get_longitude())
        elif key == 'marker_label':
            for marker in self.markers.values():
                marker.set_label_mode(value)
            pip = getattr(self.get_application(), 'pip_window', None)
            if pip is not None and pip.get_visible():
                pip.sync_aircraft()
        elif key == 'altitude_perspective':
            for marker in self.markers.values():
                marker.altitude_perspective = value
                marker.area.queue_draw()
        elif key == 'speed':
            self.radar_decoration.queue_draw()
            self._render_details()
            self._render_list()
        elif key == 'pip_always_on_top':
            pip = getattr(self.get_application(), 'pip_window', None)
            if pip is not None:
                pip.set_always_on_top(value)
        elif key == 'enable_hover':
            for marker in self.markers.values():
                marker.update(marker.plane, marker.selected, value, self.settings['speed'])
            self._rebuild_airports()
        elif key == 'monitor_metar_favorites':
            if value:
                self.weather.favorites_changed()
        elif key in ('history', 'photos'):
            self._render_details()

    def _open_startup_dialog(self):
        """Native Libadwaita modal; the already painted app stays visible and dimmed."""
        if self._startup_finished or not self.settings['startup_splash']:
            return GLib.SOURCE_REMOVE
        # Adw.Dialog requires libadwaita 1.5+. Older systems still run without
        # the optional preparation screen instead of failing at launch.
        if not hasattr(Adw, 'Dialog'):
            return GLib.SOURCE_REMOVE
        try:
            dialog = Adw.Dialog()
            dialog.set_title(_('Preparing radar'))
            dialog.set_content_width(370)
            dialog.set_can_close(True)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            content.set_margin_top(26)
            content.set_margin_bottom(24)
            content.set_margin_start(28)
            content.set_margin_end(28)
            picture = Gtk.Image.new_from_icon_name('airplane-mode-symbolic')
            picture.set_pixel_size(48)
            content.append(picture)
            heading = make_label('AeroScope', 'section-title')
            heading.set_halign(Gtk.Align.CENTER)
            content.append(heading)
            subtitle = make_label(_('Receiving the first positions to start aircraft animation…'),
                                  'dim-label', wrap=True)
            subtitle.set_justify(Gtk.Justification.CENTER)
            content.append(subtitle)
            self._startup_label = make_label(_('Waiting for first request · 0 of 3'), 'dim-label')
            self._startup_label.set_halign(Gtk.Align.CENTER)
            content.append(self._startup_label)
            self._startup_fraction = Gtk.ProgressBar()
            self._startup_fraction.set_fraction(0)
            content.append(self._startup_fraction)
            btn = Gtk.Button(label=_('Show map now'))
            btn.add_css_class('flat')
            btn.connect('clicked', lambda *_: self._finish_startup())
            btn.set_halign(Gtk.Align.CENTER)
            content.append(btn)
            dialog.set_child(content)
            dialog.connect('closed', self._startup_dialog_closed)
            self._startup_dialog = dialog
            dialog.present(self)
        except Exception:
            # Startup decoration must never prevent the radar from opening.
            self._startup_dialog = None
        return GLib.SOURCE_REMOVE

    def _startup_dialog_closed(self, *_):
        # Esc / close button is equivalent to skipping; polling continues.
        self._startup_dialog = None
        self._startup_label = None
        self._startup_fraction = None
        self._startup_finished = True

    def _update_startup(self):
        if self._startup_finished or self._startup_dialog is None:
            return
        count = min(3, self._successful_polls)
        if self._startup_label:
            messages = {0: _('Waiting for first request · 0 of 3'),
                        1: _('First position received · 1 of 3'),
                        2: _('Warming up radar and aircraft · 2 of 3'),
                        3: _('Radar ready · 3 of 3')}
            self._startup_label.set_text(messages[count])
        if self._startup_fraction:
            self._startup_fraction.set_fraction(count / 3)
        if count >= 3:
            GLib.timeout_add(180, self._finish_startup)

    def _finish_startup(self):
        if self._startup_finished:
            return GLib.SOURCE_REMOVE
        self._startup_finished = True
        dialog = self._startup_dialog
        self._startup_dialog = None
        self._startup_label = None
        self._startup_fraction = None
        if dialog is not None:
            dialog.close()
        return GLib.SOURCE_REMOVE

    def _startup_watchdog(self):
        self._finish_startup()
        return GLib.SOURCE_REMOVE

    def _initial_refresh(self):
        # Never turn the login-only monitor into a full radar by accident.
        if self._sync_regional_cadence():
            self.refresh()
        return GLib.SOURCE_REMOVE

    def _viewport_changed(self, *_):
        if self.settings['tower']:
            self.radar_decoration.queue_draw()
        if self.settings['clock_ring']:
            self.clock_decoration.queue_draw()
        # GTK notifies many times during drags and smooth zoom. Debounce; do not
        # query external services for each frame or while framing history.
        if self._history_camera or self._route_camera or time.monotonic() < self._view_suppressed_until:
            return
        self._view_dirty = True
        if self._view_timer:
            GLib.source_remove(self._view_timer)
        self._view_timer = GLib.timeout_add(850, self._view_settled)

    def _view_settled(self):
        self._view_timer = 0
        if self._history_camera or self._route_camera or not self._sync_regional_cadence():
            return GLib.SOURCE_REMOVE
        self._view_dirty = False
        view = self._visible_plan()
        # METAR/SIGMET follow the settled map region even when the ADS-B
        # positions remain inside the buffered 250 NM area (no regional HTTP).
        self.weather.region_updated()
        self._rebuild_airports()
        if self._query_anchor and viewport_inside_radius(view, self._query_anchor):
            # Local redraw, zero network calls while the visible map is inside
            # the buffered 250 NM circle. A fresh snapshot arrives on timer.
            self._render_list()
            self.coverage_label.set_text(_('250 NM coverage · cached area'))
            return GLib.SOURCE_REMOVE
        if self.busy:
            self._pending_refresh = True
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        if now < self._cooldown_until:
            self.set_status(_('API rate limit: waiting before next request.'), True)
            return GLib.SOURCE_REMOVE
        # Prevent repeated zoom/pan gestures from consuming the API quota.
        wait = max(0, self._minimum_request_gap() - (now - self._last_api_request))
        if wait > 0 and not self.demo:
            self._view_timer = GLib.timeout_add(int(wait * 1000) + 100, self._view_settled)
            self.coverage_label.set_text(_('New area · waiting for rate limit…'))
            return GLib.SOURCE_REMOVE
        self.refresh()
        return GLib.SOURCE_REMOVE

    def _visible_plan(self):
        width = max(350, self.map.get_width())
        height = max(300, self.map.get_height())
        return coverage_for_view(
            self.viewport.get_latitude(), self.viewport.get_longitude(),
            self.viewport.get_zoom_level(), width, height,
            max_queries=1, max_radius=250)

    def _set_history_mode(self, enabled):
        self._history_camera = enabled
        if not enabled:
            self._view_suppressed_until = time.monotonic() + .3

    def _adjust_sidebar(self):
        self.sidebar_pane.set_position(225 if (self.selected_hex or self.selected_airport or self.selected_sigmet or self.selected_weather_station) else 450)

    def _sync_marker_selection(self):
        for marker in self.markers.values():
            marker.set_selected(marker.plane.hex == self.selected_hex)
        if self._global_selected_marker is not None:
            self._global_selected_marker.set_selected(
                self._global_selected_marker.plane.hex == self.selected_hex)
        for code, button in getattr(self, '_airport_marker_buttons', {}).items():
            if code == self.selected_airport:
                button.add_css_class('selected-location')
            else:
                button.remove_css_class('selected-location')
        weather = getattr(self, 'weather', None)
        if weather is not None:
            for view in weather.views:
                view.sync_selection()
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None and pip.get_visible():
            pip.sync_airport_selection()
        if self.settings['tower']:
            self.radar_decoration.queue_draw()
        if self.settings['clock_ring']:
            self.clock_decoration.queue_draw()

    def _clear_global_selection(self):
        """Discard only the temporary world-wide aircraft marker."""
        if self._global_selected_marker is not None:
            self.marker_layer.remove_marker(self._global_selected_marker.marker)
            self._global_selected_marker = None
        self._global_selected_aircraft = None

    def _sync_global_selection_marker(self):
        """Show a worldwide emergency fix until the regional feed catches up.

        Never inject worldwide records into self.records or Visíveis counts.
        The temporary marker is deliberately not included in live tracks.
        """
        plane = self._global_selected_aircraft
        if plane is None or self.selected_hex != plane.hex or plane.hex in self.markers:
            if self._global_selected_marker is not None:
                self.marker_layer.remove_marker(self._global_selected_marker.marker)
                self._global_selected_marker = None
            return
        if self._global_selected_marker is None:
            marker = AircraftMarker(
                plane, self.select_plane, self.settings['enable_hover'],
                self.settings['speed'], self.settings['altitude_perspective'],
                label_mode=self.settings['marker_label'])
            marker.set_favorite(is_favorite(self.favorites, plane.registration, plane.hex))
            marker.set_alert(self._effective_aircraft_alert(plane),
                             self.settings['enable_hover'], self.settings['speed'])
            marker.set_selected(True)
            self.marker_layer.add_marker(marker.marker)
            self._global_selected_marker = marker

    def focus_global_aircraft(self, plane):
        """Navigate from Emergências without switching sidebar tabs.

        Selection and the last global fix must remain available even if the
        regional request has not yet returned, fails or lacks this aircraft.
        """
        self._clear_global_selection()
        self.move_to(plane.lat, plane.lon,
                     _('Aircraft {value0}').format(value0=plane.flight or plane.registration or plane.hex.upper()),
                     10, animated=True)
        self._global_selected_aircraft = plane
        self.selected_sigmet = None
        self.selected_hex = plane.hex
        self.selected_airport = None
        self.selected_weather_station = None
        self._sync_global_selection_marker()
        self._sync_marker_selection()
        self._render_list()
        self._render_details()
        self._draw_trail()
        self._adjust_sidebar()
        if self.settings['clock_ring']:
            self.clock_decoration.queue_draw()

    def _selected_aircraft(self):
        """Prefer fresh regional data to an earlier worldwide emergency fix."""
        plane = self.records.get(self.selected_hex)
        if plane is not None:
            return plane
        cached = self._global_selected_aircraft
        return cached if cached is not None and cached.hex == self.selected_hex else None

    def _highlight_plane(self, hexid, active):
        if active:
            if self.hover_hex and self.hover_hex != hexid and self.hover_hex in self.markers:
                self.markers[self.hover_hex].set_highlighted(False)
            self.hover_hex = hexid
        elif self.hover_hex == hexid:
            self.hover_hex = None
        marker = self.markers.get(hexid)
        if marker:
            marker.set_highlighted(active)

    def _list_pointer(self, controller, _x, _y, hexid, entered):
        self._highlight_plane(hexid, entered)

    def _effective_regional_mode(self):
        app = self.get_application()
        pip = getattr(app, 'pip_window', None)
        return regional_mode(
            started=self._regional_tracking_started,
            main_visible=self.get_visible(),
            pip_visible=bool(pip is not None and pip.get_visible()),
            visible_seconds=self.settings['refresh'],
            background_seconds=self.settings['refresh_background'])

    def _sync_regional_cadence(self):
        mode, seconds = self._effective_regional_mode()
        now = time.monotonic()
        if (mode, seconds) != self._regional_mode:
            old_mode = self._regional_mode
            self._regional_mode = (mode, seconds)
            if seconds:
                self.poll_seconds = seconds
                if mode == 'foreground':
                    # On reopening the map, refresh immediately if we had
                    # disabled regional polling or were only in the tray.
                    self._next_poll_due = now if old_mode is not None else self._next_poll_due
                elif mode == 'background':
                    self._next_poll_due = now + seconds
            else:
                self._next_poll_due = float('inf')
        return seconds > 0

    def _timer_refresh(self):
        enabled = self._sync_regional_cadence()
        now = time.monotonic()
        if (enabled and not self._history_camera and not self._route_camera
                and not self.busy and now >= self._next_poll_due
                and now >= self._cooldown_until):
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def _clear_app_cache(self):
        clear_cache()
        self.photo_info.clear()
        self.photo_widgets.clear()
        self.photo_errors.clear()
        self.history_info.clear()
        self.route_cache.clear()
        self._clear_route_visual()
        self._clear_archive_layers()
        self._set_history_mode(False)
        self.notify(_('Temporary data cleared. GNOME map cache preserved.'))

    def _clear_all_trails(self):
        self.trails.clear()
        self._clear_archive_layers()
        self._draw_trail()
        self._render_details()
        self.notify(_('Session tracks cleared.'))


    def _create_airport_marker_button(self, code: str, tooltip: str, callback, css_class='airport-marker', on_context=None):
        button = Gtk.Button()
        button.add_css_class(css_class)
        if code == self.selected_airport:
            button.add_css_class('selected-location')
        button.set_cursor_from_name('zoom-in')
        if self.settings.get('enable_hover', True):
            button.set_tooltip_text(tooltip)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        content.add_css_class('airport-marker-content')

        icon = Gtk.Label(label='🛫')
        icon.add_css_class('airport-marker-icon')
        content.append(icon)

        code_label = Gtk.Label(label=code)
        code_label.add_css_class('airport-marker-code')
        content.append(code_label)

        button.set_child(content)
        button.connect('clicked', callback)
        if on_context is not None:
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)
            right_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            right_click.connect('pressed', lambda gesture, count, x, y:
                                on_context(button, x, y))
            button.add_controller(right_click)
        return button

    def _rebuild_airports(self):
        """Show airport codes and, when available, real NOAA METAR categories.

        Airport markers remain present even when the NOAA layer is disabled,
        empty or temporarily unavailable. We never make an HTTP call here.
        """
        from .airport_weather_badge import airport_marker_text, airport_metar_tooltip, metar_badge
        self.airport_layer.remove_all()
        self._airport_marker_buttons = {}
        if not self.settings['show_airports']:
            return
        bounds = self._visible_plan().bounds
        enabled = bool(self.settings.get('weather_metar'))
        for iata, info in AIRPORTS.items():
            icao, name, a_lat, a_lon = info
            if not is_on_screen(a_lat, a_lon, bounds):
                continue
            report = self.weather.cached_metar(icao) if enabled else None
            mark = Shumate.Marker.new()
            mark.set_location(a_lat, a_lon)
            tooltip = airport_metar_tooltip(name, iata, icao, report, enabled=enabled)
            button = self._create_airport_marker_button(
                iata, tooltip, lambda _button, code=iata: self._center_airport(code),
                on_context=lambda widget, x, y, code=iata:
                    self.show_airport_context_menu(code, widget, x, y))
            if iata in self.favorite_airports:
                favorite_icon = Gtk.Label(label='★')
                favorite_icon.add_css_class('airport-favorite-star')
                button.get_child().append(favorite_icon)
            category = metar_badge(report) if enabled else None
            if category:
                button.add_css_class('airport-weather-active')
                button.add_css_class('metar-' + category.lower())
                content = button.get_child()
                category_label = Gtk.Label(label=category)
                category_label.add_css_class('airport-weather-category')
                content.append(category_label)
            mark.set_child(button)
            self.airport_layer.add_marker(mark)
            self._airport_marker_buttons[iata] = button

    def select_weather_station(self, metar):
        """Inspect regional NOAA METARs without a registered airport."""
        self._clear_global_selection()
        self._clear_route_visual()
        self._clear_archive_layers()
        self._set_history_mode(False)
        self.selected_hex = None
        self.selected_airport = None
        self.selected_sigmet = None
        self.selected_weather_station = metar
        self.follow = False
        self._sync_marker_selection()
        self._draw_trail()
        self._render_list()
        self._render_details()
        self._adjust_sidebar()
        if getattr(self, 'detail_scroll', None) is not None:
            self.detail_scroll.get_vadjustment().set_value(0)

    def select_sigmet(self, sigmet):
        """Display a NOAA aviation warning in the existing sidebar inspector.

        This does not change the active Visíveis/Favoritos/Emergências tab or
        request any extra data. It works with the main map and the PiP.
        """
        self._clear_global_selection()
        self._clear_route_visual()
        self._clear_archive_layers()
        self._set_history_mode(False)
        self.selected_hex = None
        self.selected_airport = None
        self.selected_weather_station = None
        self.selected_sigmet = sigmet
        self.follow = False
        self._sync_marker_selection()
        self._draw_trail()
        self._render_list()
        self._render_details()
        self._adjust_sidebar()
        if getattr(self, 'detail_scroll', None) is not None:
            self.detail_scroll.get_vadjustment().set_value(0)

    def select_airport(self, iata):
        if iata not in AIRPORTS:
            return
        self._clear_global_selection()
        self._clear_route_visual()
        self.selected_weather_station = None
        self.selected_airport = iata
        self.selected_sigmet = None
        self.selected_hex = None
        self._sync_marker_selection()
        self.follow = False
        self._clear_archive_layers()
        self._set_history_mode(False)
        self._draw_trail()
        self._render_list()
        self._render_details()
        self._adjust_sidebar()

    def notify(self, text):
        # GeoClue/IP are shared by both views. Never display the response
        # behind a visible mini-map (the main window may be hidden).
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None and pip.get_visible() and hasattr(pip, 'notify'):
            pip.notify(text)
        else:
            self.toast.add_toast(Adw.Toast.new(str(text)))

    def set_status(self, text, error=False):
        # Use GNOME's native title/subtitle rather than reserving a toolbar
        # across the entire width of the map. Keep strings short enough for a
        # compact header; full error details are still available via --debug.
        message = str(text).replace('\n', ' ').strip()
        if error:
            message = '⚠ ' + message
        if self.demo and _('Demo') not in message:
            message += ' · Demo'
        anchor = getattr(self, '_query_anchor', None)
        if anchor is not None:
            if 'NM' not in message:
                message += ' · 250 NM'
            message += f' · {anchor[0]:.2f}, {anchor[1]:.2f}'
        self.window_title.set_subtitle(message)

    def _auto_refresh(self):
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def _async(self, job, done):
        future = EXECUTOR.submit(job)
        def finish(fut):
            try:
                result, error = fut.result(), None
            except Exception as ex:
                # Preserve HTTP 429 metadata for the rate-limit backoff.
                result, error = None, ex
            GLib.idle_add(done, result, error)
        future.add_done_callback(finish)

    def _minimum_request_gap(self):
        # Warm-up intervals also protect manual refresh / map navigation; after
        # any error, return to the configured interval until the next launch.
        return startup_poll_interval(self.poll_seconds, self._successful_polls,
                                     failed=self._warmup_failed)

    def refresh(self):
        if self.busy:
            self._pending_refresh = True
            return
        now = time.monotonic()
        if not self.demo and now < self._cooldown_until:
            self.set_status(_('ADSB.lol rate limit: updates temporarily paused.'), True)
            return
        minimum_gap = self._minimum_request_gap()
        if not self.demo and self._last_api_request and now - self._last_api_request < minimum_gap:
            # Identical throttle for timer, manual update, and map movement.
            self._next_poll_due = min(self._next_poll_due, self._last_api_request + minimum_gap + 0.1)
            self.set_status(_('New request waiting for minimum interval ({value0:g} s).').format(value0=minimum_gap))
            return
        if self._history_camera:
            self._clear_archive_layers()
            self._set_history_mode(False)
        if self._route_camera:
            self._exit_route_camera()
        self.busy = True
        self._pending_refresh = False
        self._last_poll = now
        self._next_poll_due = float('inf')  # next due is set when this request finishes
        self._active_request_started = time.monotonic()
        self.request_number += 1
        req = self.request_number
        view = self._visible_plan()
        # Keep the original query center while its 250NM circle covers the screen.
        if self._query_anchor is None or not viewport_inside_radius(view, self._query_anchor):
            center = view.center
        else:
            center = self._query_anchor
        self._pending_anchor = center
        self._coverage = view
        self._coverage_complete = viewport_inside_radius(view, center, reserve_nm=0)
        self.center = center
        self.center_name = f'Radar: {center[0]:.3f}, {center[1]:.3f}'
        self.location_label.set_text(self.center_name)
        self.coverage_label.set_text(_('250 NM radius · 1 request') +
                                     (' · cobertura parcial neste zoom' if not self._coverage_complete else ''))
        self._rebuild_airports()
        self.set_status(_('Updating aircraft (250 NM)…'))
        if self.demo:
            self.tick += 1
            GLib.timeout_add(300, self._demo_done, req, center)
        else:
            self._last_api_request = time.monotonic()
            self._async(lambda: fetch_visible_area(((center[0], center[1], 250),)),
                        lambda result, err: self._refresh_done(req, result, err))

    def _demo_done(self, req, center):
        self._refresh_done(req, (demo_aircraft(*center, self.tick), 1, 1), None)
        return GLib.SOURCE_REMOVE

    def _refresh_done(self, req, result, error):
        if req != self.request_number:
            return GLib.SOURCE_REMOVE
        completed_at = time.monotonic()
        elapsed = (completed_at - self._active_request_started
                   if self._active_request_started else 0.0)
        self._active_request_started = 0.0
        self.busy = False
        if error:
            self._warmup_failed = True
            self._finish_startup()  # do not block the user behind an unavailable API
            if isinstance(error, RateLimitError) or '429' in str(error):
                retry = getattr(error, 'retry_after', 120)
                self._cooldown_until = time.monotonic() + retry
                self._next_poll_due = self._cooldown_until
                self.set_status(_('ADSB.lol: HTTP 429 rate limit; paused for {value0} seconds.').format(value0=retry), True)
            else:
                # Do not retry aggressively if connectivity fails.
                self._next_poll_due = time.monotonic() + max(30, self.poll_seconds)
                self._successful_polls = 0
                self.set_status(_('Refresh failed: {value0}').format(value0=error), True)
        else:
            # Exclude failed/429 calls from the latency forecast. The UI
            # receives the callback after network/JSON processing completes.
            self._request_latency.observe(elapsed)
            self._successful_polls += 1
            next_seconds = startup_poll_interval(self.poll_seconds, self._successful_polls,
                                                 failed=self._warmup_failed)
            self._next_poll_due = completed_at + next_seconds
            self._animation_window = flight_animation_duration(
                next_seconds, self._request_latency.estimate)
            logging.getLogger('aeroscope.motion').debug(
                _('Response in %.2fs; recent average %.2fs; next request in %.1fs; animation %.2fs'), elapsed, self._request_latency.estimate,
                next_seconds, self._animation_window)
            self._update_startup()
            self._query_anchor = self._pending_anchor
            planes, successful, count = result
            # Preserve positions in the whole circle. The map clips markers
            # naturally, and the left-hand list follows the visible viewport.
            self._apply_planes(planes)
            # Start the first NOAA lookup as soon as the first regional radar
            # response arrives. Do not wait for the weather 30-second timer or
            # the end of the three-stage radar splash.
            self.weather.region_updated()
            visible = [p for p in planes if is_on_screen(p.lat, p.lon, self._visible_plan().bounds)]
            complete = viewport_inside_radius(self._visible_plan(), self._query_anchor, reserve_nm=0)
            self._coverage_complete = complete
            warning = ' · cobertura parcial' if not complete or successful < count else ''
            self.set_status(_('{value0} visible · {value1} ').format(value0=len(visible), value1=time.strftime('%H:%M:%S'))
                            + ('· DEMO' if self.demo else '· ADSB.lol') + warning)
        if self._pending_refresh:
            self._pending_refresh = False
            if self._sync_regional_cadence():
                GLib.timeout_add(100, self._view_settled)
        return GLib.SOURCE_REMOVE

    def _pan_to_aircraft(self, lat, lon):
        """Gently move the camera after selection using Libshumate's native animation.

        Existing aircraft-marker transitions use a separate timer and are not
        affected. This navigation does not change the current zoom level.
        """
        self._stop_keyboard_pan()
        current_lat = self.viewport.get_latitude()
        current_lon = self.viewport.get_longitude()
        separation = distance_nm(current_lat, current_lon, lat, lon)
        if separation < 0.005:
            return
        # Short hops should feel snappy; longer hops need a little more time.
        # Do not create a multi-second flyover (or excessive tile requests).
        duration_ms = min(800, max(400, int(420 + separation * 1.0)))
        self._camera_transition_generation += 1
        generation = self._camera_transition_generation
        self._camera_transition_until = time.monotonic() + duration_ms / 1000.0
        self._view_suppressed_until = self._camera_transition_until + .25
        if self._view_timer:
            GLib.source_remove(self._view_timer)
            self._view_timer = 0
        if hasattr(self.map, 'stop_go_to'):
            self.map.stop_go_to()
        zoom = self.viewport.get_zoom_level()
        if hasattr(self.map, 'go_to_full_with_duration'):
            self.map.go_to_full_with_duration(lat, lon, zoom, duration_ms)
        elif hasattr(self.map, 'go_to'):
            # Compatibility with older versions of libshumate.
            if hasattr(self.map, 'set_go_to_duration'):
                self.map.set_go_to_duration(duration_ms)
            self.map.go_to(lat, lon)
        else:
            self.map.center_on(lat, lon)
        GLib.timeout_add(duration_ms + 250, self._camera_transition_completed, generation)

    def _camera_transition_completed(self, generation):
        if generation != self._camera_transition_generation:
            return GLib.SOURCE_REMOVE
        self._camera_transition_until = 0.0
        # Refresh local markers/list after the move. The normal geographic
        # buffer and rate limiter still decide whether a network call is due.
        self._view_settled()
        return GLib.SOURCE_REMOVE

    def _center_on_animation(self, lat, lon):
        # While switching selected aircraft, do not let automatic follow snap
        # the camera and interrupt the short Libshumate transition.
        if time.monotonic() < self._camera_transition_until:
            return
        # Following a moving marker is a camera action, not a user pan.
        self._view_suppressed_until = time.monotonic() + .25
        self.map.center_on(lat, lon)

    def _animation_tick(self):
        """One GLib timer for *all* moving aircraft, only while needed."""
        if not self.settings['animate_aircraft']:
            self._animation_source = 0
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        still_moving = False
        for marker in self.markers.values():
            if marker.animation_step(now):
                still_moving = True
        if self.follow and self.selected_hex in self.markers and not (self._history_camera or self._route_camera):
            selected = self.markers[self.selected_hex]
            if selected.transition is not None:
                self._center_on_animation(selected.marker.get_latitude(), selected.marker.get_longitude())
        if still_moving and self.settings['clock_ring'] and self.selected_hex:
            self.clock_decoration.queue_draw()
        if not still_moving:
            self._animation_source = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _start_animation_timer(self):
        if not self._animation_source and self.settings['animate_aircraft'] and any(
                m.transition is not None for m in self.markers.values()):
            # 25 FPS; cheap location updates, no repeated silhouette redraw.
            self._animation_source = GLib.timeout_add(40, self._animation_tick)

    def _effective_aircraft_alert(self, plane):
        """Combine local and world-wide emergencies using exact ICAO24."""
        monitor = self.monitor_panel
        if monitor is None:
            return classify_alert(plane.squawk, plane.emergency)
        return effective_alert(
            plane, monitor._global_rows, monitor._global_checked_at,
            self.settings['emergencies_interval'])

    def _refresh_visible_alerts(self):
        """Immediate redraw when the world-wide query returns new squawks."""
        for marker in self.markers.values():
            marker.set_alert(self._effective_aircraft_alert(marker.plane),
                             self.settings['enable_hover'], self.settings['speed'])
        if self._global_selected_marker is not None:
            marker = self._global_selected_marker
            marker.set_alert(self._effective_aircraft_alert(marker.plane),
                             self.settings['enable_hover'], self.settings['speed'])
        self._render_list()
        if self._selected_aircraft() is not None:
            self._render_details()

    def _apply_planes(self, planes):
        now = time.monotonic()
        new = {p.hex: p for p in planes}
        for hexid, marker in list(self.markers.items()):
            if hexid not in new:
                self._sweep_pending.pop(hexid, None)
                self._sweep_virtual.pop(hexid, None)
                self.marker_layer.remove_marker(marker.marker)
                del self.markers[hexid]
        for plane in planes:
            trail = self.trails[plane.hex]
            if trail and (now - trail[-1][2] > 200 or
                          abs(trail[-1][0] - plane.lat) + abs(trail[-1][1] - plane.lon) > 1.8):
                trail.clear()
            if trail:
                previous = trail[-1]
                # Under ~150 m position jitter would cause artificial spinning;
                # for long jumps the sample may belong to a different flight.
                separation = distance_nm(previous[0], previous[1], plane.lat, plane.lon)
                age = now - previous[2]
                if 0.08 <= separation <= 20 and age <= 180:
                    from .geoview import initial_bearing
                    self.bearings[plane.hex] = initial_bearing(previous[0], previous[1], plane.lat, plane.lon)
                elif separation > 20:
                    self.bearings.pop(plane.hex, None)
            if not trail or abs(trail[-1][0] - plane.lat) + abs(trail[-1][1] - plane.lon) > .00015:
                trail.append((plane.lat, plane.lon, now))
            if plane.hex not in self.markers:
                m = AircraftMarker(plane, self.select_plane,
                                   self.settings['enable_hover'], self.settings['speed'],
                                   self.settings['altitude_perspective'],
                                   on_context=self.show_aircraft_context_menu,
                                   label_mode=self.settings['marker_label'])
                self.markers[plane.hex] = m
                self.marker_layer.add_marker(m.marker)
            marker = self.markers[plane.hex]
            marker.set_favorite(is_favorite(self.favorites, plane.registration, plane.hex))
            marker.set_alert(self._effective_aircraft_alert(plane),
                             self.settings['enable_hover'], self.settings['speed'])
            # The normal mode interpolates each new confirmed ADS-B fix.
            # Scan mode is different: keep the *latest target* in memory,
            # but never move an existing marker until the beam reaches it.
            # Compare against the last received fix, NOT the frozen sprite.
            buffered = self._sweep_pending.get(plane.hex)
            previous_fix = buffered[0] if buffered is not None else marker.plane
            changed_fix = distance_nm(previous_fix.lat, previous_fix.lon,
                                      plane.lat, plane.lon) > .0005
            if self._tower_sweep_enabled():
                if marker.transition is not None:
                    # Finish the visible glide only until its current instant.
                    # A new snapshot cannot continue the old animation.
                    marker.animation_step(now)
                    marker.transition = None
                if changed_fix:
                    old_virtual = self._sweep_virtual.get(plane.hex)
                    origin = (old_virtual.sample(now)[0] if old_virtual is not None else
                              (marker.marker.get_latitude(), marker.marker.get_longitude()))
                    # Only interpolate between actually received coordinates.
                    # The sampled location is kept in memory until beam passage.
                    self._sweep_virtual[plane.hex] = PositionTransition(
                        origin, (plane.lat, plane.lon), now, self._animation_window)
                    self._sweep_pending[plane.hex] = (
                        plane, self.bearings.get(plane.hex, plane.track))
                marker.update(plane, plane.hex == self.selected_hex,
                              self.settings['enable_hover'], self.settings['speed'],
                              bearing=marker.bearing, position_mode='keep')
            else:
                self._sweep_pending.pop(plane.hex, None)
                target = marker.transition.end if marker.transition is not None else (
                    marker.marker.get_latitude(), marker.marker.get_longitude())
                changed = distance_nm(target[0], target[1],
                                      plane.lat, plane.lon) > .0005
                marker.update(plane, plane.hex == self.selected_hex,
                              self.settings['enable_hover'], self.settings['speed'],
                              self.bearings.get(plane.hex),
                              position_mode=(('smooth' if self.settings['animate_aircraft'] else 'snap')
                                             if changed else 'keep'),
                              timestamp=now, duration=self._animation_window)
        self.records = new
        self.dashboard.update_aircraft()
        self._sync_global_selection_marker()
        self._last_live_snapshot_at = time.time()
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None and pip.get_visible():
            pip.sync_aircraft()
        # The regional ADS-B snapshot already contains information about some
        # favorite aircraft. Feed it to the watchlist immediately, without an
        # extra global request or waiting for the Favoritos tab to refresh.
        if self.monitor_panel is not None:
            self.monitor_panel.update_from_live(planes)
        if self.hover_hex not in self.markers:
            self.hover_hex = None
        self._start_animation_timer()
        if self.selected_hex and self.selected_hex in new and self.follow:
            m = self.markers[self.selected_hex].marker
            self._center_on_animation(m.get_latitude(), m.get_longitude())
        self._render_list()
        self._render_details()
        self._draw_trail()
        if self.settings['clock_ring'] and self.selected_hex:
            self.clock_decoration.queue_draw()
        if (self._suggestions_visible() and not self._search_committed
                and self.search.get_text().strip()):
            self._render_search_suggestions()

    def _render_list(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        bounds = self._visible_plan().bounds
        sorted_planes = sorted((p for p in self.records.values() if is_on_screen(p.lat, p.lon, bounds)),
                              key=lambda p: (p.flight or p.registration or p.hex))
        self.visible_stack_page.set_title(_('Visible ({value0})').format(value0=len(sorted_planes)))
        if not sorted_planes:
            row = Gtk.ListBoxRow()
            label = make_label(_('No aircraft with a valid position in this area.'), 'dim-label', True)
            label.set_margin_top(20)
            label.set_margin_bottom(20)
            label.set_margin_start(18)
            label.set_margin_end(18)
            row.set_child(label)
            self.listbox.append(row)
            return
        for p in sorted_planes[:240]:
            row = Gtk.ListBoxRow()
            row.add_css_class('aircraft-list-row')
            if p.hex == self.selected_hex:
                row.add_css_class('selected-aircraft')
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            content.set_margin_start(16)
            content.set_margin_end(13)
            content.set_margin_top(10)
            content.set_margin_bottom(10)
            # The list uses the same aircraft-category silhouette as the map.
            icon = Gtk.DrawingArea()
            icon.set_content_width(30)
            icon.set_content_height(30)
            icon.set_valign(Gtk.Align.CENTER)
            def draw_icon(_area, cr, _width, _height, model=p.model, track=p.track,
                          alert_level=self._effective_aircraft_alert(p).level):
                cr.scale(30 / 56, 30 / 56)
                paint_aircraft(cr, model, track, alert_level=alert_level,
                               altitude_ft=(p.altitude_ft if self.settings['altitude_perspective'] else float('nan')))
            icon.set_draw_func(draw_icon)
            content.append(icon)
            block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            block.set_hexpand(True)
            name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            name_row.append(make_label(p.flight or p.registration or p.hex.upper(), 'aircraft-name', True))
            alert = self._effective_aircraft_alert(p)
            if alert.level in ('warning', 'critical'):
                alert_symbol = make_label('●', 'aircraft-alert-badge')
                alert_symbol.add_css_class('critical' if alert.level == 'critical' else 'warning')
                alert_symbol.set_tooltip_text(alert.label)
                name_row.append(alert_symbol)
            if is_favorite(self.favorites, p.registration, p.hex):
                favorite_star = make_label('★', 'favorite-star')
                favorite_star.set_tooltip_text(_('Favorite aircraft'))
                name_row.append(favorite_star)
            block.append(name_row)
            block.append(make_label(f'{aircraft_name(p.model)} · {p.registration or p.hex.upper()}', 'dim-label', True))
            content.append(block)
            metric = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            al = make_label(p.altitude, 'aircraft-alt')
            al.set_halign(Gtk.Align.END)
            metric.append(al)
            speed = make_label(format_speed(p.speed_kts, self.settings['speed']), 'dim-label')
            speed.set_halign(Gtk.Align.END)
            metric.append(speed)
            content.append(metric)
            button = Gtk.Button(child=content)
            button.add_css_class('list-button')
            button.connect('clicked', lambda _b, hexid=p.hex: self.select_plane(hexid))
            hover = Gtk.EventControllerMotion()
            hover.connect('enter', lambda ctl, x, y, hexid=p.hex:
                          self._list_pointer(ctl, x, y, hexid, True))
            hover.connect('leave', lambda ctl, hexid=p.hex:
                          self._list_pointer(ctl, 0, 0, hexid, False))
            button.add_controller(hover)
            row.set_child(button)
            self.listbox.append(row)

    def select_plane(self, hexid):
        if (self._global_selected_aircraft is not None
                and hexid != self._global_selected_aircraft.hex):
            self._clear_global_selection()
        p = self.records.get(hexid)
        if p is None and self._global_selected_aircraft is not None:
            if hexid == self._global_selected_aircraft.hex:
                p = self._global_selected_aircraft
        if not p:
            self.notify(_('Aircraft is no longer in this area.'))
            return
        if self.selected_hex != hexid:
            self._clear_route_visual()
            self._clear_archive_layers()
            self._set_history_mode(False)
        self.selected_airport = None
        self.selected_sigmet = None
        self.selected_weather_station = None
        self.selected_hex = hexid
        self._sync_marker_selection()
        # During scan mode, center what is actually on screen, not a newer
        # buffered coordinate that the sweeping beam has yet to reveal.
        marker = self.markers.get(hexid) or self._global_selected_marker
        if self._tower_sweep_enabled() and marker is not None:
            self._pan_to_aircraft(marker.marker.get_latitude(), marker.marker.get_longitude())
        else:
            self._pan_to_aircraft(p.lat, p.lon)
        self._render_list()
        self._render_details()
        self._draw_trail()
        self._adjust_sidebar()
        if self.settings['clock_ring']:
            self.clock_decoration.queue_draw()
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None and pip.get_visible():
            pip.sync_aircraft()  # Immediate selected clock and marker appearance.
        for m in self.markers.values():
            m.update(m.plane, m.plane.hex == hexid, self.settings['enable_hover'], self.settings['speed'])

    def _append_metar_report(self, metar):
        """Shared NOAA details for airports and independent weather stations."""
        explanation = describe_metar(metar)
        self.detail_box.append(make_label(_('In plain language'), 'section-title'))
        self.detail_box.append(make_label(explanation.condition, None, True))
        for label, value in explanation.fields:
            self.detail_box.append(line_row(label, value))
        if not explanation.fields:
            self.detail_box.append(make_label(
                _('This report does not contain enough data to describe the weather.'),
                'dim-label', True))
        self.detail_box.append(line_row(_('Observed'), metar.observed or _('Time not provided')))
        original = Gtk.Expander(label=_('View original METAR (technical code)'))
        original.set_margin_top(8)
        original.set_child(make_label(
            metar.raw or _('Original code unavailable.'), 'dim-label', True))
        self.detail_box.append(original)
        self.detail_box.append(make_label(
            _('Source: NOAA Aviation Weather Center. Weather observation, not a forecast. Do not use alone for flight decisions.'), 'footnote', True))

    def _append_location_header(self, name, lat, lon, kind, airport_code=None, station_code=None):
        """Shared compact location inspector header (airport or METAR station).

        Reuse the aircraft inspector pattern: short title + center + close.
        Keep actions out of the scrolling content and never let a long name
        force the resizable sidebar wider than the user selected.
        """
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        header.set_hexpand(True)
        title = make_label(name, 'section-title')
        title.set_hexpand(True)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_width_chars(1)
        title.set_max_width_chars(22)
        title.set_tooltip_text(name)
        header.append(title)

        center = icon_button('find-location-symbolic',
                             _('Center {value0} on map').format(value0=kind),
                             lambda *_: self._pan_to_aircraft(lat, lon), 'flat')
        header.append(center)
        if station_code is not None:
            is_starred = station_code in self.favorite_stations
            star = icon_button('starred-symbolic' if is_starred else 'non-starred-symbolic',
                               _('Remove station from favorites') if is_starred else _('Add station to favorites'),
                               lambda *_: self._toggle_station_favorite(self.selected_weather_station), 'flat')
            header.append(star)
        if airport_code is not None:
            is_starred = airport_code in self.favorite_airports
            star = icon_button('starred-symbolic' if is_starred else 'non-starred-symbolic',
                               _('Remove airport from favorites') if is_starred else _('Add airport to favorites'),
                               lambda *_: self._toggle_airport_favorite(airport_code), 'flat')
            header.append(star)
        close = icon_button('window-close-symbolic',
                            _('Close details for {value0}').format(value0=kind),
                            lambda *_: self._clear_selected(), 'flat')
        header.append(close)
        self.detail_box.append(header)

    def _append_location_sigmet(self, lat, lon):
        """Show overlapping aviation advisories *alongside* the METAR.

        SIGMET coverage is horizontal only; it does not change the METAR's
        VFR/IFR category or imply that the phenomenon is at runway level.
        """
        from .sigmet_readable import describe_sigmet
        state, advisories = self.weather.sigmet_coverage(lat, lon)
        heading = make_label(_('SIGMET advisories · NOAA'), 'section-title')
        heading.set_margin_top(8)
        self.detail_box.append(heading)
        if state == 'loading':
            self.detail_box.append(make_label(_('Checking SIGMET coverage…'), 'dim-label'))
            return
        if state == 'error':
            self.detail_box.append(make_label(
                _('SIGMET lookup unavailable; coverage cannot be confirmed.'), 'dim-label', True))
            return
        if state == 'invalid':
            self.detail_box.append(make_label(_('Position unavailable for SIGMET lookup.'), 'dim-label'))
            return
        if not advisories:
            self.detail_box.append(make_label(
                _('No matching active SIGMET was returned for this location.'), 'dim-label', True))
            return
        self.detail_box.append(make_label(
            _('A SIGMET area covers this location horizontally. The reported phenomenon may be aloft or forecast, not necessarily occurring at the airport.'),
            'footnote', True))
        for index, advisory in enumerate(advisories[:6]):
            decoded = describe_sigmet(advisory)
            group = Gtk.Expander(label=decoded.icon + ' ' + decoded.title)
            group.set_expanded(index == 0)  # Show the first validity bar immediately.
            group.set_margin_top(4)
            lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            lines.append(make_label(decoded.description, None, True))
            from .validity_widget import sigmet_timeline
            timeline = sigmet_timeline(advisory)
            if timeline is not None:
                lines.append(timeline)
            for label, value in decoded.fields:
                if timeline is None or label not in (_('Start of validity'), _('End of validity')):
                    lines.append(line_row(label, value))
            bulletin = Gtk.Expander(label=_('View original SIGMET (technical bulletin)'))
            bulletin.set_child(make_label(advisory.text or
                                          _('Original bulletin not provided by NOAA.'),
                                          'dim-label', True))
            lines.append(bulletin)
            group.set_child(lines)
            self.detail_box.append(group)
        if len(advisories) > 6:
            self.detail_box.append(make_label(
                _('Plus {value0} additional SIGMET advisories.').format(value0=len(advisories) - 6),
                'dim-label', True))
        self.detail_box.append(make_label(
            _('Advisory coverage is approximate and does not replace official preflight briefings.'),
            'footnote', True))

    def _render_details(self):
        # Selection changes can originate from map polygons, their symbols or
        # another sidebar item. Repaint on *changes*, not on every radar tick.
        selected = (self.selected_sigmet if not self.selected_airport
                    and not self.selected_hex else None)
        if selected is not getattr(self, '_last_sigmet_visual_selected', None):
            self._last_sigmet_visual_selected = selected
            weather = getattr(self, 'weather', None)
            if weather is not None:
                for view in weather.views:
                    if view.sigmet_canvas.get_visible():
                        view.sigmet_canvas.queue_draw()
        child = self.detail_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.detail_box.remove(child)
            child = nxt
        if self.selected_sigmet is not None and not self.selected_airport and not self.selected_hex:
            from .sigmet_readable import describe_sigmet
            advisory = self.selected_sigmet
            decoded = describe_sigmet(advisory)
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            heading = make_label(decoded.icon + ' ' + decoded.title, 'section-title', True)
            heading.set_hexpand(True)
            header.append(heading)
            close = icon_button('window-close-symbolic', _('Close SIGMET advisory'),
                                lambda *_: self._clear_selected())
            close.add_css_class('flat')
            header.append(close)
            self.detail_box.append(header)
            self.detail_box.append(make_label(_('Aviation weather advisory · NOAA'), 'dim-label', True))
            self.detail_box.append(make_label(decoded.description, None, True))
            from .validity_widget import sigmet_timeline
            timeline = sigmet_timeline(advisory)
            if timeline is not None:
                self.detail_box.append(timeline)
            for label, value in decoded.fields:
                if timeline is None or label not in (_('Start of validity'), _('End of validity')):
                    self.detail_box.append(line_row(label, value))
            self.detail_box.append(make_label(
                _('The drawn area is approximate. A SIGMET describes observed or forecast conditions that may affect flight operations.'),
                'footnote', True))
            original = Gtk.Expander(label=_('View original SIGMET (technical bulletin)'))
            original.set_margin_top(8)
            original.set_child(make_label(advisory.text or
                                          _('Original bulletin not provided by NOAA.'),
                                          'dim-label', True))
            self.detail_box.append(original)
            self.detail_box.append(make_label(
                _('Source: NOAA Aviation Weather Center. Advisory information; not a substitute for official preflight briefings.'),
                'footnote', True))
            return
        if (self.selected_weather_station is not None and not self.selected_hex
                and not self.selected_airport and self.selected_sigmet is None):
            metar = self.selected_weather_station
            self._append_location_header(_('Weather station · ') + metar.station,
                                         metar.lat, metar.lon, _('station'),
                                         station_code=metar.station)
            self.detail_box.append(make_label(_('METAR observation · NOAA'), 'dim-label', True))
            self.detail_box.append(line_row(_('ICAO station'), metar.station))
            self.detail_box.append(line_row(_('Position'), f'{metar.lat:.4f}, {metar.lon:.4f}'))
            if not metar.raw and not metar.details:
                state, fresh, error = self.weather.get_airport_metar(metar.station)
                if fresh is not None:
                    self.selected_weather_station = fresh
                    self._append_metar_report(fresh)
                elif state == 'loading':
                    self.detail_box.append(make_label(_('Checking METAR…'), 'dim-label'))
                elif state == 'error':
                    self.detail_box.append(make_label(_('METAR temporarily unavailable.'), 'dim-label', True))
                else:
                    self.detail_box.append(make_label(_('No recent METAR available.'), 'dim-label', True))
            else:
                self._append_metar_report(metar)
            self._append_location_sigmet(metar.lat, metar.lon)
            return
        plane = self._selected_aircraft()
        if plane is None:
            if self.selected_hex and self.history_info.get(self.selected_hex):
                header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                title = make_label('Voos arquivados · ' + self.selected_hex.upper(), 'section-title')
                title.set_hexpand(True)
                header.append(title)
                header.append(icon_button('window-close-symbolic', _('Close details'),
                                          lambda *_: self._clear_selected()))
                self.detail_box.append(header)
                self.detail_box.append(make_label(_('ADSB.aero records; these are not live positions.'), 'dim-label', True))
                for entry in self.history_info[self.selected_hex][:8]:
                    flight_id = entry.get('flight_id')
                    if not flight_id:
                        continue
                    time_label = str(entry.get('start_ts') or '')[:16].replace('T', ' ')
                    label = f'{entry.get("callsign") or "Voo"} · {time_label} UTC'
                    button = Gtk.Button(child=make_label(label, wrap=True))
                    button.connect('clicked', lambda *_args, fid=flight_id: self.show_historical_track(fid))
                    self.detail_box.append(button)
            elif self.selected_airport:
                iata = self.selected_airport
                icao, name, lat, lon = AIRPORTS[iata]
                self._append_location_header(name, lat, lon, _('airport'), airport_code=iata)
                self.detail_box.append(line_row(_('Code'), f'{iata} / {icao}'))
                self.detail_box.append(line_row(_('Position'), f'{lat:.4f}, {lon:.4f}'))
                # Station-specific METAR does not depend on the global map layer.
                metar_state, metar, metar_error = self.weather.get_airport_metar(icao)
                self.detail_box.append(make_label('Meteorologia · NOAA', 'section-title'))
                if metar_state == 'loading':
                    self.detail_box.append(make_label(_('Checking METAR…'), 'dim-label'))
                elif metar_state == 'error':
                    self.detail_box.append(make_label(_('METAR unavailable: request failed.'), 'dim-label', True))
                elif metar_state == 'ready' and metar:
                    self._append_metar_report(metar)
                elif metar_state == 'ready':
                    self.detail_box.append(make_label(_('No recent METAR available for this airport.'),
                                                      'dim-label', True))
                else:
                    self.detail_box.append(make_label(_('METAR unavailable for this code.'), 'dim-label'))
                self._append_location_sigmet(lat, lon)
                departures = Gtk.Button(label=_('View arrivals and departures'))
                departures.add_css_class('suggested-action')
                departures.set_tooltip_text(_("Open the airport's public page on Flightradar24"))
                departures.connect('clicked', lambda *_: self._view_website(
                    airport_board_url(iata), title=f'Chegadas e partidas · {iata}'))
                self.detail_box.append(departures)
                self.detail_box.append(make_label(
                    _('Flight information provided by Flightradar24 on an external page.'),
                    'footnote', True))
            else:
                self.detail_box.append(make_label(_('Aircraft details'), 'section-title'))
                self.detail_box.append(make_label(_('Select an aircraft on the map or in the list.'), 'dim-label', True))
            return
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        header.set_hexpand(True)
        flight = make_label(plane.flight or plane.registration or plane.hex.upper(), 'section-title')
        flight.set_hexpand(True)
        flight.set_ellipsize(Pango.EllipsizeMode.END)
        flight.set_width_chars(1)
        flight.set_max_width_chars(22)
        header.append(flight)

        # The selected aircraft's compact actions share one row. Toggle state
        # is visible, and the original follow semantics remain unchanged.
        self.follow_btn = Gtk.ToggleButton(
            icon_name='media-playback-pause-symbolic' if self.follow else 'media-playback-start-symbolic')
        self.follow_btn.set_tooltip_text(_('Stop following') if self.follow else _('Follow aircraft'))
        self.follow_btn.add_css_class('flat')
        self.follow_btn.set_active(self.follow)
        self.follow_btn.connect('toggled', self._follow_changed)
        header.append(self.follow_btn)

        center = icon_button('find-location-symbolic', _('Center aircraft on map'),
                             lambda *_: self._pan_to_aircraft(plane.lat, plane.lon), 'flat')
        header.append(center)
        favorited = is_favorite(self.favorites, plane.registration, plane.hex)
        star = icon_button('starred-symbolic' if favorited else 'non-starred-symbolic',
                           _('Remove from favorites') if favorited else _('Add to watchlist'),
                           lambda *_: self._toggle_favorite(plane))
        star.add_css_class('flat')
        header.append(star)
        close = icon_button('window-close-symbolic', _('Close details'), lambda *_: self._clear_selected())
        close.add_css_class('flat')
        header.append(close)
        self.detail_box.append(header)
        if plane.hex not in self.records and self._global_selected_aircraft is not None:
            self.detail_box.append(make_label(
                _('Last position from worldwide emergency check; waiting for regional radar.'),
                'dim-label', True))
        self.detail_box.append(make_label(f'{plane.registration or _("No registration")} · {aircraft_name(plane.model)}', 'dim-label', True))
        self.detail_box.append(line_row(_('Category'), aircraft_category(plane.model)))
        self.detail_box.append(line_row('Altitude', plane.altitude))
        self.detail_box.append(line_row(_('Speed'), format_speed(plane.speed_kts, self.settings['speed'])))
        self.detail_box.append(make_label(speed_details(plane.speed_kts, self.settings['speed']), 'footnote', True))
        self.detail_box.append(line_row(_('Heading'), f'{round(plane.track)}°'))
        self.detail_box.append(line_row(_('Position'), f'{plane.lat:.4f}, {plane.lon:.4f}'))
        self.detail_box.append(line_row('ICAO24', plane.hex.upper()))
        alert = self._effective_aircraft_alert(plane)
        if alert.level != 'none':
            self.detail_box.append(line_row(_('Transmitted alert'), alert.label))
            self.detail_box.append(make_label(alert.detail, 'footnote', True))
        self.detail_box.append(line_row(_('Track from this session'), _('{value0} positions').format(value0=len(self.trails[plane.hex]))))
        self.detail_box.append(make_label(_('Green track: session · blue: historical archive · dashed amber: estimated route.'),
                                          'footnote', True))
        self._add_route_details(plane)
        self._add_enrichment(plane)

    def show_aircraft_context_menu(self, hexid, widget, x, y, parent_window=None):
        """Only marker right-click opens this context menu (main map or PiP).

        If the image is not cached, opening the menu asynchronously checks it.
        A pending request is reused, never repeated for each right-click.
        """
        plane = self.records.get(hexid)
        if plane is None:
            return
        photo = self.photo_info.get(hexid)
        has_photo = isinstance(photo, dict) and bool(photo.get('image') or photo.get('link'))
        favorited = is_favorite(self.favorites, plane.registration, plane.hex)
        popover = Gtk.Popover()
        popover.add_css_class('aircraft-context-menu')
        popover.set_has_arrow(True)
        popover.set_position(Gtk.PositionType.RIGHT)
        popover.set_parent(widget)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for side in ('start', 'end', 'top', 'bottom'):
            getattr(content, 'set_margin_' + side)(5)

        def item(text, icon, callback, enabled=True):
            button = Gtk.Button()
            button.add_css_class('flat')
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            row.set_margin_start(5)
            row.set_margin_end(9)
            row.append(Gtk.Image.new_from_icon_name(icon))
            label = Gtk.Label(label=text, xalign=0)
            row.append(label)
            button.set_child(row)
            button.set_sensitive(enabled)
            button.connect('clicked', lambda *_: self._activate_context_action(popover, callback))
            content.append(button)
            return button

        def follow():
            self.select_plane(hexid)
            self.follow = True
            self._render_details()  # Keep the Follow toggle in sync.

        item(_('Center aircraft on map'), 'find-location-symbolic',
             lambda: self._center_aircraft_from_menu(hexid))
        item(_('Follow aircraft'), 'media-playback-start-symbolic', follow)
        item(_('Unfavorite') if favorited else _('Add to favorites'),
             'starred-symbolic' if favorited else 'non-starred-symbolic',
             lambda: self._toggle_favorite(plane))
        item(_('Remove floating panel') if self.dashboard.has('aircraft', hexid)
             else _('Create floating panel'), 'view-grid-symbolic',
             lambda: (self.dashboard.remove('aircraft', hexid)
                      if self.dashboard.has('aircraft', hexid)
                      else self.dashboard.add('aircraft', hexid)))

        def preview():
            cached = self.photo_info.get(hexid)
            if not isinstance(cached, dict):
                return
            try:
                if cached.get('image'):
                    texture = self._decode_photo(hexid, cached['image'])
                    self._show_photo_preview(hexid, cached, texture,
                                             plane.registration, parent_window=parent_window)
                elif cached.get('link'):
                    # The catalogue may supply a photo without a usable thumbnail.
                    self._view_website(cached['link'], 'Fotografia · ' + plane.registration)
            except (RuntimeError, ValueError, TypeError, OSError) as exc:
                PHOTO_LOG.warning('Context photo unavailable for %s: %s', hexid, exc)
                self.notify(_('Could not open the photo.'))

        wants_photo_lookup = bool(self.settings.get('photos') and not has_photo and
                                  hexid not in self.photo_info and hexid not in self.photo_errors)
        photo_button = item(_('View photo') if has_photo else
                            'Buscando fotografia…' if wants_photo_lookup else _('Photo unavailable'),
                            'image-x-generic-symbolic', preview, has_photo)
        photo_label = photo_button.get_child().get_last_child()
        popover.set_child(content)
        if wants_photo_lookup:
            if not hasattr(self, '_context_photo_waiters'):
                self._context_photo_waiters = {}
            self._context_photo_waiters.setdefault(hexid, []).append(
                (popover, photo_button, photo_label))
            # Avoid a second fetch if the details panel is already fetching.
            if hexid not in self.photo_pending:
                self.photo_pending.add(hexid)
                self._async(lambda: self._fetch_photo(hexid, plane.registration),
                            lambda result, error: self._photo_done(hexid, result, error))
        protect_context_menu(popover, widget, GLib.idle_add, self._detach_context_popover)
        popover.popup()

    @staticmethod
    def _detach_context_popover(popover):
        """Detach only after GTK finishes dispatching its close event.

        Unparenting synchronously in the `closed` signal can invalidate the
        pointer used by GTK's ancestor/event-controller traversal.
        """
        try:
            if popover.get_parent() is not None:
                popover.unparent()
        except (RuntimeError, TypeError):
            pass
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _activate_context_action(popover, action):
        """Do not remove/rebuild a marker from inside its popover click event."""
        popover.popdown()

        def perform():
            action()
            return GLib.SOURCE_REMOVE

        GLib.idle_add(perform)

    def _center_aircraft_from_menu(self, hexid):
        plane = self.records.get(hexid)
        if plane is None:
            return
        self.select_plane(hexid)
        self._pan_to_aircraft(plane.lat, plane.lon)

    def _center_airport(self, iata):
        if iata in AIRPORTS:
            self.select_airport(iata)
            _icao, _name, lat, lon = AIRPORTS[iata]
            self._pan_to_aircraft(lat, lon)

    def show_airport_context_menu(self, iata, widget, x, y):
        """Right-click the fixed airport marker to open its contextual actions."""
        if iata not in AIRPORTS:
            return
        self.select_airport(iata)  # Right click opens the inspector, too.
        popover = Gtk.Popover()
        popover.add_css_class('aircraft-context-menu')
        popover.set_has_arrow(True)
        popover.set_position(Gtk.PositionType.RIGHT)
        popover.set_parent(widget)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for side in ('start', 'end', 'top', 'bottom'):
            getattr(content, 'set_margin_' + side)(5)

        def item(label, icon, action):
            button = Gtk.Button()
            button.add_css_class('flat')
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            row.set_margin_start(5)
            row.set_margin_end(9)
            row.append(Gtk.Image.new_from_icon_name(icon))
            row.append(Gtk.Label(label=label, xalign=0))
            button.set_child(row)
            button.connect('clicked', lambda *_: self._activate_context_action(popover, action))
            content.append(button)

        item(_('Center airport on map'), 'find-location-symbolic',
             lambda: self._center_airport(iata))
        starred = iata in self.favorite_airports
        item(_('Remove airport from favorites') if starred else _('Add airport to favorites'),
             'starred-symbolic' if starred else 'non-starred-symbolic',
             lambda: self._toggle_airport_favorite(iata))
        item(_('Remove floating panel') if self.dashboard.has('airport', iata)
             else _('Create floating panel'), 'view-grid-symbolic',
             lambda: self.dashboard.remove('airport', iata)
             if self.dashboard.has('airport', iata) else self.dashboard.add('airport', iata))
        popover.set_child(content)
        protect_context_menu(popover, widget, GLib.idle_add, self._detach_context_popover)
        popover.popup()

    def _toggle_airport_favorite(self, iata):
        if iata not in AIRPORTS:
            return
        next_favorites = set(self.favorite_airports)
        if iata in next_favorites:
            next_favorites.remove(iata)
            message = _('{value0} removed from airport favorites.').format(value0=iata)
        else:
            next_favorites.add(iata)
            message = _('{value0} added to airport favorites.').format(value0=iata)
        try:
            save_airport_favorites(next_favorites)
        except (OSError, ValueError) as exc:
            self.notify(_('Could not save airport favorites: {value0}').format(value0=exc))
            return
        self.favorite_airports = next_favorites
        self.weather.favorites_changed()
        self._rebuild_airports()
        self._render_details()
        if self.monitor_panel is not None:
            self.monitor_panel._render_favorites()
        self.notify(message)

    def _toggle_station_favorite(self, metar):
        """Save an independent NOAA station without using an aircraft watchlist slot."""
        if metar is None:
            return
        code = str(metar.station).strip().upper()
        updated = dict(self.favorite_stations)
        if code in updated:
            del updated[code]
            message = _('{value0} removed from station favorites.').format(value0=code)
        else:
            updated[code] = (metar.lat, metar.lon)
            message = _('{value0} added to station favorites.').format(value0=code)
        try:
            save_station_favorites(updated)
        except (OSError, ValueError, TypeError) as exc:
            self.notify(_('Could not save station favorites: {value0}').format(value0=exc))
            return
        self.favorite_stations = updated
        self.weather.favorites_changed()
        self._render_details()
        for view in self.weather.views:
            view.update()
        if self.monitor_panel is not None:
            self.monitor_panel._render_favorites()
        self.notify(message)

    def _center_station(self, code, position=None):
        position = position if position is not None else self.favorite_stations.get(code)
        if position is None:
            return False
        from .weather_data import Metar
        lat, lon = position
        report = self.weather.cached_metar(code)
        if report is None:
            report = Metar(code, lat, lon, '', 'N/D', '', {})
        self.select_weather_station(report)
        self._pan_to_aircraft(lat, lon)
        self.weather.get_airport_metar(code)
        return True

    def show_station_context_menu(self, metar, widget, x, y):
        self.select_weather_station(metar)  # Right click also opens the inspector.
        popover = Gtk.Popover()
        popover.add_css_class('aircraft-context-menu')
        popover.set_has_arrow(True)
        popover.set_position(Gtk.PositionType.RIGHT)
        popover.set_parent(widget)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for side in ('start', 'end', 'top', 'bottom'):
            getattr(content, 'set_margin_' + side)(5)

        def item(label, icon, action):
            button = Gtk.Button()
            button.add_css_class('flat')
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            row.set_margin_start(5)
            row.set_margin_end(9)
            row.append(Gtk.Image.new_from_icon_name(icon))
            row.append(Gtk.Label(label=label, xalign=0))
            button.set_child(row)
            button.connect('clicked', lambda *_: self._activate_context_action(popover, action))
            content.append(button)

        item(_('Center weather station on map'), 'find-location-symbolic',
             lambda: (self.select_weather_station(metar), self._pan_to_aircraft(metar.lat, metar.lon)))
        starred = metar.station in self.favorite_stations
        item(_('Remove station from favorites') if starred else _('Add station to favorites'),
             'starred-symbolic' if starred else 'non-starred-symbolic',
             lambda: self._toggle_station_favorite(metar))
        item(_('Remove floating panel') if self.dashboard.has('station', metar.station)
             else _('Create floating panel'), 'view-grid-symbolic',
             lambda: self.dashboard.remove('station', metar.station)
             if self.dashboard.has('station', metar.station)
             else self.dashboard.add('station', metar.station, position=(metar.lat, metar.lon)))
        popover.set_child(content)
        protect_context_menu(popover, widget, GLib.idle_add, self._detach_context_popover)
        popover.popup()

    def _toggle_favorite(self, plane):
        reg = (plane.registration or '').strip().upper()
        if reg:
            kind, value = 'registration', reg
        else:
            kind, value = 'icao', plane.hex.upper()
        matching = [f for f in self.favorites if
                    (f.kind == 'icao' and f.value == plane.hex.upper()) or
                    (f.kind == 'registration' and reg and f.value == reg)]
        try:
            if matching:
                keys_to_remove = {f.key for f in matching}
                updated = [f for f in self.favorites if f.key not in keys_to_remove]
                message = _('{value0} removed from watchlist.').format(value0=value)
            else:
                updated = add_favorite(self.favorites, kind, value,
                                       (plane.flight or '').strip())
                message = _('{value0} added to watchlist.').format(value0=value)
            save_favorites(updated)
        except (OSError, ValueError) as exc:
            self.notify(_('Could not change favorite: {value0}').format(value0=exc))
            return
        self.favorites = updated
        self._favorites_changed()
        self.notify(message)

    def emit_monitor_alert(self, title, message, notification_id, action, sound=False):
        """Native freedesktop desktop notification; never spawns a background daemon."""
        try:
            item = Gio.Notification.new(str(title))
            item.set_body(str(message))
            item.set_priority(Gio.NotificationPriority.HIGH)
            item.set_default_action(action)
            self.get_application().send_notification(notification_id, item)
            logging.getLogger('aeroscope.monitor').info(_('Notification: %s'), title)
        except (AttributeError, RuntimeError, TypeError) as exc:
            logging.getLogger('aeroscope.monitor').warning(
                _('Could not deliver system notification: %s'), exc)
        if sound:
            self.play_monitor_alarm()

    def play_monitor_alarm(self):
        """Play a single desktop event sound where available; otherwise system bell.

        Do not ignore the user's muted / Do Not Disturb desktop preferences.
        No bundled audio or additional Python packages are required.
        """
        try:
            binary = shutil.which('canberra-gtk-play')
            if binary:
                subprocess.Popen([binary, '--id=dialog-warning', '--description=AeroScope'],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, close_fds=True)
                return
            display = Gdk.Display.get_default()
            if display is not None:
                display.beep()
        except (OSError, RuntimeError, AttributeError) as exc:
            logging.getLogger('aeroscope.monitor').warning(_('Audio unavailable: %s'), exc)

    def _favorites_changed(self):
        """Update labels and map stars without resetting ongoing animations."""
        for marker in self.markers.values():
            marker.set_favorite(is_favorite(self.favorites,
                                            marker.plane.registration, marker.plane.hex))
        self._render_list()
        self._render_details()
        if self.monitor_panel is not None:
            self.monitor_panel.update_from_live(self.records.values())
            self.monitor_panel._render_favorites()

    def show_monitor(self, tab='favorites'):
        self.sidebar_stack.set_visible_child_name(tab)
        self.present()

    def _route_key(self, plane):
        return (plane.hex.lower(), (plane.flight or '').strip().upper())

    def _add_route_details(self, plane):
        """Show an association, not an actual flight plan or ATC waypoints."""
        title = make_label(_('Origin and destination'), 'section-title')
        title.set_margin_top(8)
        self.detail_box.append(title)
        callsign = (plane.flight or '').strip().upper()
        if not callsign:
            self.detail_box.append(make_label(_('No callsign available for route lookup.'),
                                              'dim-label', True))
            return
        if self.demo:
            self.detail_box.append(make_label(_('Airport association unavailable in demo mode.'),
                                              'dim-label', True))
            return
        key = self._route_key(plane)
        if self.route_visible and self._route_display_key not in (None, key):
            self._clear_route_visual()
        cached, route, error = self.route_cache.get(key)
        if not cached:
            if key not in self.route_pending and time.monotonic() >= self._routes_cooldown_until:
                self.route_pending.add(key)
                self._async(lambda: fetch_live_route(callsign, plane.lat, plane.lon),
                            lambda result, exc, route_key=key: self._route_done(route_key, result, exc))
            label = (_('Checking association on ADSB.lol…') if key in self.route_pending
                     else _('Requests temporarily paused; try again later.'))
            self.detail_box.append(make_label(label, 'dim-label', True))
            return
        if route is None:
            self.detail_box.append(make_label(
                error or _('ADSB.lol did not identify origin/destination for this callsign.'),
                'dim-label', True))
            if time.monotonic() >= self._routes_cooldown_until:
                retry = Gtk.Button(label='Tentar identificar novamente')
                retry.add_css_class('flat')
                retry.connect('clicked', lambda *_: self._retry_route_lookup(key))
                self.detail_box.append(retry)
            return
        # Compact GNOME-style two-line entries; long airport names wrap in the
        # narrow inspector instead of widening the entire sidebar.
        for direction, airport in ((_('Origin'), route.origin), (_('Destination'), route.destination)):
            entry = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            entry.append(make_label(f'{direction} · {airport.code}', 'aircraft-name'))
            entry.append(make_label(airport.name, 'dim-label', True))
            self.detail_box.append(entry)
        if route.plausible is False:
            self.detail_box.append(make_label(
                _('The provider flagged this association as unlikely. Check the airports.'),
                'footnote', True))
        else:
            self.detail_box.append(make_label(
                _('Probable route by callsign — not a flight plan or confirmed trajectory.'),
                'footnote', True))
        if route_has_geometry(route):
            self.detail_box.append(make_label(
                _('Geographic distance between airports: {value0:,.0f} km').format(value0=distance_nm(route.origin.lat, route.origin.lon, route.destination.lat, route.destination.lon) * 1.852).replace(',', '.'),
                'footnote', True))
        else:
            self.detail_box.append(make_label(
                _('The API identified the airports but did not provide sufficient coordinates to draw a reliable geographic line.'), 'footnote', True))
            return
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        toggle = Gtk.ToggleButton(label=_('Show estimated route'))
        toggle.set_active(self.route_visible)
        toggle.set_hexpand(True)
        toggle.connect('toggled', self._route_toggled)
        controls.append(toggle)
        full = Gtk.Button(label=_('View complete route'))
        full.connect('clicked', lambda *_: self._fit_live_route(route, plane))
        controls.append(full)
        self.detail_box.append(controls)
        if self._route_camera:
            back = Gtk.Button(label=_('Return to live radar'))
            back.connect('clicked', lambda *_: self._leave_route_view())
            self.detail_box.append(back)
            self.detail_box.append(make_label(
                _('Map updates paused while fitting the entire route.'),
                'footnote', True))

    def _retry_route_lookup(self, key):
        # Manual retry only; clear the negative cache and restart the normal
        # selection-triggered lookup, respecting any provider cooldown.
        if time.monotonic() < self._routes_cooldown_until or key in self.route_pending:
            return
        self.route_cache.remove(key)
        self._render_details()

    def _route_done(self, key, result, error):
        self.route_pending.discard(key)
        if isinstance(error, RateLimitError):
            self._routes_cooldown_until = time.monotonic() + error.retry_after
            logging.getLogger('aeroscope.routes').warning(_('Route request limit: %s'), error)
        elif error:
            logging.getLogger('aeroscope.routes').warning(_('Route request %s: %s'), key, error)
        self.route_cache.put(key, result if isinstance(result, ProbableRoute) else None, error)
        if (self.route_visible and route_has_geometry(result)
                and self.selected_hex in self.records
                and self._route_key(self.records[self.selected_hex]) == key):
            self._draw_probable_route(result)
        if self.selected_hex and self.selected_hex in self.records and self._route_key(self.records[self.selected_hex]) == key:
            self._render_details()
        return GLib.SOURCE_REMOVE

    def _clear_route_visual(self):
        if self._route_camera:
            self._exit_route_camera()
        if hasattr(self, 'route_layers'):
            for layer in self.route_layers:
                layer.remove_all()
            self.route_airport_layer.remove_all()
        self.route_visible = False
        self._route_display_key = None
        self._route_camera = False
        self._route_previous_view = None

    def _draw_probable_route(self, route):
        if self.selected_hex in self.records:
            self._route_display_key = self._route_key(self.records[self.selected_hex])
        points = great_circle_points(route.origin.lat, route.origin.lon,
                                     route.destination.lat, route.destination.lon)
        for layer in self.route_layers:
            layer.remove_all()
        for layer, segment in zip(self.route_layers, map_segments(points)):
            for lat, lon in segment:
                layer.add_node(Shumate.Coordinate.new_full(lat, lon))
        self.route_airport_layer.remove_all()
        for airport, direction in ((route.origin, _('Origin')), (route.destination, _('Destination'))):
            pin = Shumate.Marker.new()
            pin.set_location(airport.lat, airport.lon)
            button = self._create_airport_marker_button(
                airport.code,
                f'{direction}: {airport.name} ({airport.code})',
                lambda *_args, a=airport: self.map.center_on(a.lat, a.lon),
                'route-airport-marker',
            )
            pin.set_child(button)
            self.route_airport_layer.add_marker(pin)

    def _route_toggled(self, button):
        self.route_visible = button.get_active()
        plane = self.records.get(self.selected_hex)
        cached, route, _ = self.route_cache.get(self._route_key(plane)) if plane else (False, None, None)
        if self.route_visible and cached and route_has_geometry(route):
            self._draw_probable_route(route)
        else:
            for layer in self.route_layers:
                layer.remove_all()
            self.route_airport_layer.remove_all()
            self._route_display_key = None
            if self._route_camera:
                self._exit_route_camera()
                GLib.idle_add(self._rerender_after_route_toggle)
        # No full details rebuild here: recreating a Gtk.ToggleButton during
        # a toggled emission can cause duplicate callbacks on some GTK builds.

    def _rerender_after_route_toggle(self):
        self._render_details()
        return GLib.SOURCE_REMOVE

    def _fit_live_route(self, route, plane):
        self.route_visible = True
        self._draw_probable_route(route)
        points = great_circle_points(route.origin.lat, route.origin.lon,
                                     route.destination.lat, route.destination.lon)
        # Include the current aircraft position without pretending it is
        # one of the waypoints on the theoretical line.
        fitted = fit_trajectory([points, [(plane.lat, plane.lon)]],
                                max(360, self.map.get_width()), max(320, self.map.get_height()))
        if not fitted:
            self.notify(_('Could not fit the estimated route.'))
            return
        if not self._route_camera:
            self._route_previous_view = (self.viewport.get_latitude(),
                                         self.viewport.get_longitude(),
                                         self.viewport.get_zoom_level())
        self._route_camera = True
        self.follow = False
        self._view_suppressed_until = time.monotonic() + 1.5
        lat, lon, zoom = fitted
        self.map.center_on(lat, lon)
        self.viewport.set_zoom_level(zoom)
        self.set_status(_('Estimated geographic route · radar updates paused'))
        self._render_details()

    def _exit_route_camera(self):
        if not self._route_camera:
            return
        self._route_camera = False
        self._view_suppressed_until = time.monotonic() + 1.0
        previous, self._route_previous_view = self._route_previous_view, None
        if previous:
            self.map.center_on(previous[0], previous[1])
            self.viewport.set_zoom_level(previous[2])
        else:
            plane = self.records.get(self.selected_hex)
            if plane:
                self.map.center_on(plane.lat, plane.lon)
                self.viewport.set_zoom_level(9)
        self._next_poll_due = time.monotonic() + 0.25

    def _leave_route_view(self):
        self._exit_route_camera()
        self._render_details()
        self.notify(_('Live radar resumed.'))

    def _add_enrichment(self, plane):
        hexid = plane.hex
        if self.settings['photos']:
            photo_title = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            photo_title.set_margin_top(8)
            label = make_label(_('Photo'), 'section-title')
            label.set_hexpand(True)
            photo_title.append(label)
            photo = self.photo_info.get(hexid)
            if isinstance(photo, dict):
                # Small icon opens the original photographer's page in WebKit.
                external = icon_button('external-link-symbolic',
                                       _('View original photo and credits'),
                                       lambda *_args, url=photo['link']:
                                       self._view_website(url, _('Original photo')))
                external.add_css_class('flat')
                photo_title.append(external)
            self.detail_box.append(photo_title)
            if isinstance(photo, dict):
                if photo.get('image'):
                    # Reuse the *same widget and texture* across periodic radar
                    # updates: no repeated image decoding, logging, or download.
                    if hexid not in self.photo_widgets:
                        try:
                            self.photo_widgets[hexid] = self._make_photo_widget(hexid, photo, plane.registration)
                        except Exception as exc:
                            PHOTO_LOG.exception(_('Failed to prepare image for %s'), hexid)
                            self.photo_errors[hexid] = _('Failed to render image: ') + str(exc)[:110]
                    if hexid in self.photo_widgets:
                        self.detail_box.append(self.photo_widgets[hexid])
                    else:
                        self.detail_box.append(make_label(self.photo_errors.get(hexid, _('Image unavailable.')),
                                                          'dim-label', True))
                else:
                    self.detail_box.append(make_label(
                        self.photo_errors.get(hexid, _('Thumbnail unavailable; view the original.')),
                        'dim-label', True))
                    self.detail_box.append(make_label('© ' + photo.get('photographer', _('Unknown author'))
                                                      + ' · Planespotters.net', 'footnote', True))
            elif hexid in self.photo_errors:
                self.detail_box.append(make_label(self.photo_errors[hexid], 'dim-label', True))
                retry = Gtk.Button(label='Tentar novamente')
                retry.connect('clicked', lambda *_: self._retry_photo(hexid))
                self.detail_box.append(retry)
            elif hexid in self.photo_info:
                self.detail_box.append(make_label(_('No photo for this registration or ICAO24.'), 'dim-label', True))
            elif self.demo:
                self.detail_box.append(make_label(_('Photos unavailable in demo mode.'), 'dim-label', True))
            else:
                self.detail_box.append(make_label(_('Checking Planespotters.net…'), 'dim-label'))
                if hexid not in self.photo_pending:
                    self.photo_pending.add(hexid)
                    registration = plane.registration
                    self._async(lambda: self._fetch_photo(hexid, registration),
                                lambda photo, error: self._photo_done(hexid, photo, error))
        if self.settings['history']:
            section = make_label(_('ADSB.aero history'), 'section-title')
            section.set_margin_top(8)
            self.detail_box.append(section)
            if hexid not in self.history_info:
                self.detail_box.append(make_label(_('Searching historical archive…') if not self.demo else
                                                  _('History unavailable in demo mode.'), 'dim-label', True))
                if hexid not in self.history_pending and not self.demo:
                    self.history_pending.add(hexid)
                    self._async(lambda: fetch_history_index(hexid),
                                lambda flights, error: self._history_done(hexid, flights, error))
            else:
                flights = self.history_info[hexid]
                if not flights:
                    self.detail_box.append(make_label(_('No archived flights found in the requested period.'), 'dim-label', True))
                for entry in flights[:5]:
                    flight_id = entry.get('flight_id')
                    if not isinstance(flight_id, str):
                        continue
                    start = str(entry.get('start_ts') or '')[:16].replace('T', ' ')
                    caption = f'{start} UTC · {entry.get("start_airport_ident") or "?"} → {entry.get("end_airport_ident") or "?"}'
                    row = Gtk.Button(label=caption)
                    row.add_css_class('flat')
                    row.connect('clicked', lambda *_args, fid=flight_id: self.show_historical_track(fid))
                    self.detail_box.append(row)
                if self.current_archive_id:
                    self.detail_box.append(make_label(_('Violet historical replay: player above the map, segments without coverage kept separate.'), 'footnote', True))

    @staticmethod
    def _decode_photo(hexid, image_bytes):
        try:
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(image_bytes))
            decoder = 'Gdk.Texture'
        except Exception as exc:
            PHOTO_LOG.warning(_('GDK could not decode photo of %s: %s. Trying GdkPixbuf.'), hexid, exc)
            gi.require_version('GdkPixbuf', '2.0')
            from gi.repository import GdkPixbuf
            loader = GdkPixbuf.PixbufLoader.new()
            loader.write(image_bytes)
            loader.close()
            texture = Gdk.Texture.new_for_pixbuf(loader.get_pixbuf())
            decoder = 'GdkPixbuf'
        PHOTO_LOG.info(_('Photo %s decoded once (%s, %sx%s)'),
                       hexid, decoder, texture.get_width(), texture.get_height())
        return texture

    @staticmethod
    def _photo_gallery_url(registration):
        # A known, public registration gallery; never use arbitrary API URLs.
        from urllib.parse import quote
        reg = (registration or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9-]{3,12}', reg):
            return None
        return 'https://www.planespotters.net/photos/reg/' + quote(reg, safe='-')

    def _make_photo_widget(self, hexid, photo, registration):
        texture = self._decode_photo(hexid, photo['image'])
        block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        picture = Gtk.Picture()
        picture.set_paintable(texture)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(-1, 180)
        thumbnail = Gtk.Button(child=picture)
        thumbnail.add_css_class('flat')
        thumbnail.add_css_class('photo-preview-button')
        thumbnail.set_tooltip_text(_('Enlarge photo'))
        thumbnail.set_cursor_from_name('zoom-in')
        thumbnail.connect('clicked', lambda *_: self._show_photo_preview(hexid, photo, texture, registration))
        block.append(thumbnail)
        block.append(make_label('© ' + photo.get('photographer', _('Unknown author'))
                                + ' · Planespotters.net', 'footnote', True))
        gallery_url = self._photo_gallery_url(registration)
        if gallery_url:
            gallery = Gtk.Button(label=_('View aircraft gallery'))
            gallery.add_css_class('flat')
            gallery.connect('clicked', lambda *_args: self._view_website(
                gallery_url, _('Photo gallery · ') + registration))
            block.append(gallery)
        return block

    def _show_photo_preview(self, hexid, photo, texture, registration, parent_window=None):
        # The public API provides a *thumbnail*, not the copyrighted original.
        # Show the cached texture only; visit Planespotters for full resolution.
        win = Adw.Window(transient_for=parent_window or self, modal=False,
                         title='Fotografia · ' + (registration or hexid.upper()),
                         default_width=820, default_height=620)
        toolbar = Adw.ToolbarView()
        win.set_content(toolbar)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title=registration or hexid.upper(), subtitle='Miniatura ampliada · Planespotters.net'))
        gallery_url = self._photo_gallery_url(registration)
        if gallery_url:
            g = icon_button('view-grid-symbolic', _('Open gallery in built-in browser'),
                            lambda *_: self._view_website(gallery_url, 'Galeria · ' + (registration or hexid)))
            header.pack_end(g)
        external = icon_button('external-link-symbolic', _('Open original photo in built-in browser'),
                               lambda *_args: self._view_website(photo['link'], _('Original photo')))
        header.pack_end(external)
        toolbar.add_top_bar(header)
        pic = Gtk.Picture()
        pic.set_paintable(texture)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        pic.set_hexpand(True)
        pic.set_vexpand(True)
        pic.set_margin_top(12)
        pic.set_margin_bottom(12)
        pic.set_margin_start(12)
        pic.set_margin_end(12)
        toolbar.set_content(pic)
        credit = make_label('© ' + photo.get('photographer', _('Unknown author'))
                            + _(' · Planespotters.net · thumbnail-resolution preview'), 'footnote', True)
        credit.set_margin_start(16)
        credit.set_margin_end(16)
        credit.set_margin_bottom(10)
        toolbar.add_bottom_bar(credit)
        win.present()
        self._photo_preview_window = win

    @staticmethod
    def _fetch_photo(hexid, registration):
        PHOTO_LOG.debug(_('Photo task started for ICAO24=%s, registration=%s'), hexid, registration)
        photo = fetch_photo_details(hexid, registration)
        if not photo:
            PHOTO_LOG.info(_('Photo task finished without a photo for %s'), hexid)
            return None
        try:
            photo['image'] = download_thumbnail(photo['src'])
        except Exception as exc:
            PHOTO_LOG.warning(_('Aircraft thumbnail %s unavailable: %s'), hexid, exc)
            photo['image'] = None
            photo['image_error'] = str(exc)
        return photo

    def _retry_photo(self, hexid):
        self.photo_widgets.pop(hexid, None)
        self.photo_info.pop(hexid, None)
        self.photo_errors.pop(hexid, None)
        if self.selected_hex == hexid:
            self._render_details()

    def _photo_done(self, hexid, photo, error):
        self.photo_pending.discard(hexid)
        self.photo_widgets.pop(hexid, None)
        if error:
            self.photo_errors[hexid] = _('Failed to retrieve photos: {value0}').format(value0=str(error)[:240])
            PHOTO_LOG.error(_('Photo lookup failed for %s: %s'), hexid, error)
        else:
            self.photo_info[hexid] = photo if isinstance(photo, dict) else None
            if isinstance(photo, dict) and photo.get('image_error'):
                self.photo_errors[hexid] = (_('Thumbnail not loaded: ') + str(photo['image_error'])[:150] + _('. Open the original photo.'))
                PHOTO_LOG.warning(_('Thumbnail %s failed: %s'), hexid, photo['image_error'])
        # Resolve any open context menus without refetching the photo.
        waiters = getattr(self, '_context_photo_waiters', {}).pop(hexid, [])
        available = (isinstance(self.photo_info.get(hexid), dict) and
                     bool(self.photo_info[hexid].get('image') or self.photo_info[hexid].get('link')))
        for popover, button, label in waiters:
            try:
                if popover.get_parent() is not None:
                    button.set_sensitive(available)
                    label.set_text(_('View photo') if available else _('Photo unavailable'))
            except (RuntimeError, AttributeError):
                pass
        self.dashboard.update_aircraft_photo(hexid)
        if self.selected_hex == hexid:
            self._render_details()
        return GLib.SOURCE_REMOVE

    def _history_done(self, hexid, flights, error):
        self.history_pending.discard(hexid)
        self.history_info[hexid] = flights if isinstance(flights, list) else []
        if error and self.selected_hex == hexid:
            self.notify(_('Could not retrieve ADSB.aero history.'))
        if self.selected_hex == hexid:
            self._render_details()
        return GLib.SOURCE_REMOVE

    def show_historical_track(self, flight_id):
        selected = self.selected_hex
        self.replay_archive_info = next(
            (item for item in self.history_info.get(selected, [])
             if item.get('flight_id') == flight_id), {})
        self.replay_aircraft_info = self.records.get(selected)
        self._async(lambda: fetch_history_replay(flight_id),
                    lambda replay, error: self._history_track_done(selected, flight_id, replay, error))
        self.notify(_('Loading archived trajectory…'))

    def _history_track_done(self, hexid, flight_id, replay, error):
        if self.selected_hex != hexid:
            return GLib.SOURCE_REMOVE
        if error:
            self.notify(_('Failed to retrieve trajectory: {value0}').format(value0=error))
            return GLib.SOURCE_REMOVE
        archive_meta = self.replay_archive_info
        aircraft_meta = self.replay_aircraft_info
        self._clear_archive_layers()
        self.replay_archive_info = archive_meta
        self.replay_aircraft_info = aircraft_meta
        self._clear_route_visual()
        if not isinstance(replay, HistoricalReplay):
            self.notify(_('No valid times or positions to replay this flight.'))
            return GLib.SOURCE_REMOVE
        color = Gdk.RGBA()
        color.parse('#8e62c8')
        for segment in replay.segments:
            layer = Shumate.PathLayer.new(self.viewport)
            layer.set_stroke_color(color)
            layer.set_stroke_width(3.0)
            layer.set_fill(False)
            try:
                layer.set_dash([3, 6])
            except (AttributeError, TypeError, ValueError):
                pass
            self.simple_map.add_overlay_layer(layer)
            self.archive_layers.append(layer)
        self.replay_track = replay
        self.replay_time = replay.start
        self.replay_running = False
        self._replay_rendered_at = None
        self.replay_play_button.set_icon_name('media-playback-start-symbolic')
        self.replay_speed.set_selected(0)
        self.replay_panel.set_visible(True)
        self.replay_marker = Shumate.Marker.new()
        first = replay.segments[0][0]
        self.replay_marker.set_location(first.lat, first.lon)
        plane = self.replay_aircraft_info
        self.replay_model = (self.replay_archive_info or {}).get('icao_type') or (plane.model if plane else '')
        self.replay_heading = replay.bearing_at(replay.start)
        self.replay_art = Gtk.DrawingArea()
        self.replay_art.set_content_width(56)
        self.replay_art.set_content_height(56)
        self.replay_art.set_draw_func(self._draw_replay_aircraft)
        self.replay_art.add_css_class('replay-aircraft-art')
        self.replay_art.set_tooltip_text(_('Archived flight aircraft; not a live position'))
        self.replay_marker.set_child(self.replay_art)
        self.replay_marker_layer.add_marker(self.replay_marker)

        info = self.replay_archive_info or {}
        flight = info.get('callsign') or (plane.flight if plane else '') or flight_id.split(':')[0].upper()
        registration = (plane.registration if plane else '') or info.get('registration') or ''
        model = aircraft_name(self.replay_model) if self.replay_model else _('Historical aircraft')
        origin = info.get('start_airport_ident') or _('Origin not identified')
        destination = info.get('end_airport_ident') or _('Destination not identified')
        self.replay_title.set_text(f'{flight} · {registration}' if registration else str(flight))
        self.replay_subtitle.set_text(f'{model}  ·  {origin} → {destination}  ·  ADSB.aero')
        self.current_archive_id = flight_id
        self._set_history_mode(True)
        # Focus the aircraft at the actual FIRST archival point, not the
        # bounding rectangle of the whole flight. Recenter action stays handy.
        self.map.center_on(first.lat, first.lon)
        if self.viewport.get_zoom_level() < 6:
            self.viewport.set_zoom_level(7)
        self.replay_chart_button.set_active(False)
        self.replay_altitude_toggle.set_active(True)
        self.replay_speed_toggle.set_active(True)
        self.replay_axis.set_selected(0)
        self._render_replay_frame()
        self._replay_last_tick = time.monotonic()
        if not self._replay_timer_id:
            self._replay_timer_id = GLib.timeout_add(100, self._replay_tick)
        self.notify(_('Historical flight loaded. Use the player or expand the chart.'))
        self._render_details()
        return GLib.SOURCE_REMOVE

    def _clear_archive_layers(self):
        self.replay_running = False
        self.replay_track = None
        self.replay_time = None
        self._replay_rendered_at = None
        self.replay_aircraft_info = None
        self.replay_archive_info = None
        if hasattr(self, 'replay_chart_button'):
            self.replay_chart_button.set_active(False)
        if self._replay_timer_id:
            GLib.source_remove(self._replay_timer_id)
            self._replay_timer_id = 0
        if getattr(self, 'replay_marker', None) is not None:
            self.replay_marker_layer.remove_marker(self.replay_marker)
            self.replay_marker = None
        if hasattr(self, 'replay_panel'):
            self.replay_panel.set_visible(False)
            self.replay_hide_live.set_active(False)
        for layer in self.archive_layers:
            self.simple_map.remove_overlay_layer(layer)
        self.archive_layers.clear()
        self.current_archive_id = None

    def _view_website(self, url, title=_('External page')):
        # Never turn arbitrary API/user text into a WebKit URL. Known services
        # only, HTTPS, no embedded third-party HTML constructed locally.
        parsed = urlsplit(url)
        allowed = {'www.planespotters.net', 'planespotters.net',
                   'www.flightradar24.com', 'data.flightradar24.com'}
        if parsed.scheme != 'https' or parsed.hostname not in allowed:
            self.notify(_('External address not authorized.'))
            return
        try:
            gi.require_version('WebKit', '6.0')
            from gi.repository import WebKit
        except (ImportError, ValueError):
            self.notify(_('WebKitGTK unavailable: opening in default browser.'))
            Gio.AppInfo.launch_default_for_uri(url, None)
            return
        win = Adw.Window(transient_for=self, modal=False, title=title,
                         default_width=1000, default_height=710)
        toolbar = Adw.ToolbarView()
        win.set_content(toolbar)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=title, subtitle=parsed.hostname))
        external = icon_button('external-link-symbolic', _('Open in default browser'),
                               lambda *_: Gio.AppInfo.launch_default_for_uri(url, None))
        header.pack_end(external)
        toolbar.add_top_bar(header)
        webview = WebKit.WebView()
        webview.load_uri(url)
        toolbar.set_content(webview)
        win.present()
        self._website_window = win

    def _map_click_pressed(self, _gesture, n_press, x, y):
        if getattr(self, '_keyboard_pan_timer', 0):
            self._stop_keyboard_pan()
        if (getattr(self, 'suggestions_revealer', None) is not None
                and self._suggestions_visible()):
            self._commit_search()
        if n_press != 1:
            self._map_press_position = None
            return
        self._map_press_position = (x, y,
                                    self.viewport.get_latitude(),
                                    self.viewport.get_longitude())

    def _map_click_cancelled(self, *_args):
        self._map_press_position = None

    def _map_click_released(self, _gesture, _n_press, x, y):
        press = self._map_press_position
        self._map_press_position = None
        if press is None:
            return
        x0, y0, lat0, lon0 = press
        # A pan gesture must NEVER dismiss the details, even if the pointer
        # lands on an empty map pixel after dragging.
        if math.hypot(x-x0, y-y0) > 8:
            return
        if (abs(self.viewport.get_latitude()-lat0) > 1e-6 or
                abs(self.viewport.get_longitude()-lon0) > 1e-6):
            return
        # Hit-test the actual GTK child: Shumate marker buttons and native
        # zoom/compass controls must retain their own click behavior.
        hit = self.map_overlay.pick(x, y, Gtk.PickFlags.DEFAULT)
        while hit is not None and hit is not self.map_overlay:
            if isinstance(hit, Gtk.Button) or hit is getattr(self, 'replay_panel', None):
                return
            hit = hit.get_parent()
        # Only an empty-map click transfers focus away from text editing.
        # Never steal focus when the user clicks a marker or a button.
        if getattr(self, 'map', None) is not None:
            self.map.grab_focus()
        if (getattr(self, 'settings', {}).get('weather_sigmet') and
                getattr(getattr(self, 'weather', None), 'noaa', None)):
            try:
                lat, lon = self.viewport.widget_coords_to_location(self.map, x, y)
                selected = self.weather.sigmet_at_location(lat, lon)
                if selected is not None:
                    self.select_sigmet(selected)
                    return
            except (AttributeError, TypeError, ValueError) as exc:
                logging.getLogger('aeroscope.weather').debug(
                    _('SIGMET: click test unavailable: %s'), exc)
        if (self.selected_hex or self.selected_airport or self.selected_sigmet
                or self.selected_weather_station):
            self._clear_selected()

    def _clear_selected(self):
        self._clear_global_selection()
        self.selected_weather_station = None
        self.selected_hex = None
        self.selected_airport = None
        self.selected_sigmet = None
        # The hour dial belongs exclusively to the selected aircraft. Remove
        # it immediately, including when the rotating sweep is switched off.
        if self.settings['clock_ring']:
            self.clock_decoration.queue_draw()
        self._clear_route_visual()
        self._clear_archive_layers()
        self.follow = False
        self._set_history_mode(False)
        self._sync_marker_selection()
        self._draw_trail()
        self._render_list()
        self._render_details()
        self._adjust_sidebar()

    def _follow_changed(self, button):
        self.follow = button.get_active()
        button.set_icon_name('media-playback-pause-symbolic' if self.follow
                             else 'media-playback-start-symbolic')
        button.set_tooltip_text(_('Stop following') if self.follow
                                else _('Follow aircraft'))

    def _draw_trail(self):
        self.trail_layer.remove_all()
        points = list(self.trails.get(self.selected_hex, []))
        if len(points) < 2:
            return
        for lat, lon, _ in points:
            self.trail_layer.add_node(Shumate.Coordinate.new_full(lat, lon))

    def zoom(self, delta):
        # Use the same native animation as mouse scroll and double-click zoom.
        if delta > 0 and self.viewport.get_zoom_level() < 18:
            self.map.zoom_in()
        elif delta < 0 and self.viewport.get_zoom_level() > 2:
            self.map.zoom_out()


    def move_to(self, lat, lon, name, zoom=9, *, animated=False):
        self._stop_keyboard_pan()
        if not (-85 < lat < 85 and -180 <= lon <= 180):
            self.notify(_('Invalid coordinates.'))
            return
        self._clear_global_selection()
        self.center = (lat, lon)
        self.center_name = name
        self.location_label.set_text(name)
        self._rebuild_airports()
        self._clear_route_visual()
        self._clear_archive_layers()
        self._set_history_mode(False)
        self._view_suppressed_until = time.monotonic() + (1.2 if animated else 1.0)
        if animated and hasattr(self.map, 'go_to_full_with_duration'):
            # Smooth native map camera, with zoom in the same transition.
            if hasattr(self.map, 'stop_go_to'):
                self.map.stop_go_to()
            self.map.go_to_full_with_duration(lat, lon, zoom, 750)
        elif animated and hasattr(self.map, 'go_to'):
            if hasattr(self.map, 'stop_go_to'):
                self.map.stop_go_to()
            self.map.go_to(lat, lon)
            self.viewport.set_zoom_level(zoom)
        else:
            self.map.center_on(lat, lon)
            self.viewport.set_zoom_level(zoom)
        self.selected_hex = None
        self.selected_airport = None
        self.selected_sigmet = None
        self.selected_weather_station = None
        self._sync_marker_selection()
        self.follow = False
        self.trail_layer.remove_all()
        self._render_details()
        self._adjust_sidebar()
        self.refresh()

    def on_search(self, *_args):
        query = self.search.get_text().strip()
        if len(query) < 2:
            self.notify(_('Enter at least two characters to search.'))
            return
        row = self.suggest_listbox.get_selected_row()
        if (self._suggestions_visible() and row is not None
                and getattr(row, '_aeroscope_result', None) is not None):
            self._activate_suggestion(row._aeroscope_result)
            return
        airport = find_airport(query)
        if airport:
            iata, info = airport
            self._activate_suggestion(next(item for item in local_suggestions(
                iata, [], AIRPORTS) if item.key == iata))
            return
        # Prefer an exact locally known flight, registration or ICAO code.
        local = local_suggestions(query, self.records.values(), {}, aircraft_name)
        exact = next((item for item in local
                      if normalized(query) in (normalized(item.title), normalized(item.key),
                                               normalized(self.records[item.key].registration))), None)
        if exact:
            self._activate_suggestion(exact)
            return
        city_matches = self._search_city_cache.get(normalized(query), [])
        if city_matches:
            self._activate_suggestion(city_matches[0])
            return
        self._commit_search()
        term = query.upper().replace(' ', '')
        kind = classify_aircraft_identifier(term)
        if kind:
            if self.settings.get('history'):
                self._start_historical_search(term)
            self.notify(_('Searching for live aircraft and historical records…')
                        if self.settings.get('history') else _('Searching live aircraft…'))
            self._async(lambda: fetch_plane(kind, term), self._plane_found)
        else:
            if self.search_busy:
                return
            self.search_busy = True
            self.notify(_('Searching city…'))
            self._async(lambda: geocode_city(query), self._city_found)

    def _city_found(self, locations, error):
        self.search_busy = False
        if error:
            self.notify(error)
        elif not locations:
            self.notify(_('City not found. Try including the state or country.'))
        else:
            city, state, country, lat, lon = locations[0]
            self.move_to(lat, lon, ', '.join(filter(None, (city, state, country))), 9)
            if len(locations) > 1:
                self.notify(_('Multiple locations found; showing the first result.'))
        return GLib.SOURCE_REMOVE

    def _plane_found(self, matches, error):
        if error:
            self.notify(error)
        elif not matches:
            self.notify(_('No position currently available for this aircraft.'))
        else:
            plane = matches[0]
            self.move_to(plane.lat, plane.lon, _('Aircraft {value0}').format(value0=plane.flight or plane.registration or plane.hex), 10)
            # Área é atualizada em seguida; salvamos seleção para o próximo lote.
            self.selected_hex = plane.hex
            self.notify(_('Aircraft found. The radar is loading the area.'))
        return GLib.SOURCE_REMOVE

    def _location_dialog_parent(self):
        # Both the main window and PiP present the EXACT SAME consent widget.
        # Only the transient parent changes to keep the prompt on the screen
        # where the user triggered geolocation.
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None and pip.get_visible():
            return pip
        return self._preferences_window if getattr(self, '_preferences_window', None) else self

    def confirm_ip_location(self, *_args):
        """Never bypass GNOME's privacy setting silently: ask before each IP lookup."""
        if self._ip_location_pending:
            self.notify(_('An approximate location request is already in progress.'))
            return
        if self.settings.get('ip_disclosure_accepted', False):
            self._start_ip_lookup()
            return
        # Avoid leaving a previous confirmation open.
        if self._ip_dialog is not None:
            self._ip_dialog.present()
            return
        parent = self._location_dialog_parent()
        dialog = IpLocationDialog(
            parent, _('Approximate IP location'),
            _('AeroScope will contact the external service ipwho.is over HTTPS. That service will see your public IP address. The position may be inaccurate, especially when using a VPN, mobile network or remote provider. AeroScope will not save your IP address or location. Continue?'),
            actions=[('proceed', _('Find location'), True),
                     ('cancel', _('Cancel'), False)],
            close_response='cancel', on_response=self._ip_permission_answer)
        self._ip_dialog = dialog
        dialog.present()

    def _ip_permission_answer(self, dialog, response):
        self._ip_dialog = None
        if response == 'proceed':
            self.settings['ip_disclosure_accepted'] = True
            save(self.settings)
            self._start_ip_lookup()

    def _start_ip_lookup(self):
        """Only called in direct response to a user accepting an IP disclosure."""
        if self._ip_location_pending:
            return
        self._ip_location_pending = True
        self.notify(_('Checking approximate location from public IP address…'))
        self._async(geolocate_by_public_ip, self._ip_location_ready)

    def _suggest_ip_location(self, reason, *, user_initiated=False):
        """Offer opt-in IP positioning; explicit retries are never session-blocked.

        Automatic suggestions are limited to once per session. A deliberate
        click on Locate after selecting "Agora não" is a fresh user request.
        Neither case makes a network request without explicit consent.
        """
        if not should_suggest_ip(self.settings, self._location_fallback_offered,
                                 self.demo, user_initiated=user_initiated):
            return
        if self._ip_dialog is not None or self._ip_location_pending:
            return
        # Never stack two modals: wait until the startup overlay has closed.
        if getattr(self, '_startup_dialog', None) is not None:
            if not self._ip_suggestion_waiting:
                self._ip_suggestion_waiting = True
                GLib.timeout_add(500, self._deferred_ip_suggestion, reason, user_initiated)
            return
        self._location_fallback_offered = True
        already_consented = self.settings.get('ip_disclosure_accepted', False)
        disclosure = (_('Would you like to use approximate IP location?') if already_consented else
                      _('This request sends your public IP address to ipwho.is and may return an inaccurate city. If you agree, AeroScope will remember your permission so this notice is not shown again. You can revoke it in Preferences. Continue?'))
        dialog = IpLocationDialog(
            self._location_dialog_parent(), _('Use approximate IP location?'),
            f'{reason}\n\n{disclosure}',
            actions=[('ip', _('Locate using IP'), True),
                     ('never', _('Do not suggest again'), False),
                     ('later', _('Not now'), False)],
            close_response='later', on_response=self._ip_suggestion_answer)
        self._ip_dialog = dialog
        dialog.present()

    def _deferred_ip_suggestion(self, reason, user_initiated=False):
        if getattr(self, '_startup_dialog', None) is not None:
            return GLib.SOURCE_CONTINUE
        self._ip_suggestion_waiting = False
        self._suggest_ip_location(reason, user_initiated=user_initiated)
        return GLib.SOURCE_REMOVE

    def _ip_suggestion_answer(self, dialog, response):
        self._ip_dialog = None
        if response == 'never':
            self.settings['suggest_ip_fallback'] = False
            save(self.settings)
        elif response == 'ip':
            self.settings['ip_disclosure_accepted'] = True
            save(self.settings)
            self._start_ip_lookup()

    def _startup_locate(self):
        # The automatic startup lookup must obey the once-per-session offer.
        self.locate(user_initiated=False)
        return GLib.SOURCE_REMOVE

    def _ip_location_ready(self, result, error):
        self._ip_location_pending = False
        if error is not None:
            self.notify(_('IP location unavailable: {value0}').format(value0=error))
        else:
            lat, lon, place = result
            self.move_to(lat, lon, _('{value0} · estimated by IP').format(value0=place), 9, animated=True)
            self._set_my_position(lat, lon)
            self.notify(_('Approximate position by IP. It may not match your physical location.'))
        return GLib.SOURCE_REMOVE

    def locate(self, *_args, force=False, user_initiated=True):
        # Every click should have an effect. GeoClue.Simple can keep the same
        # client alive after the first lookup; re-use that verified position
        # when the user just wants to bring the camera back to themselves.
        if self._last_system_fix is not None and not force:
            lat, lon = self._last_system_fix
            self.move_to(lat, lon, _('My location (GeoClue)'), 10,
                         animated=True)
            self._set_my_position(lat, lon)
            self.notify(_('Centering on last known position again.'))
            return GLib.SOURCE_REMOVE
        if self._last_location_fix is not None and not force:
            # Previous session-local IP result may be the only available fix
            # when GNOME/GeoClue location services are disabled. Reuse it
            # without transmitting the public IP again or claiming GPS accuracy.
            lat, lon = self._last_location_fix
            self.move_to(lat, lon, _('Last approximate IP location'), 9,
                         animated=True)
            self._set_my_position(lat, lon)
            self.notify(_('Centering on last approximate IP location.'))
            return GLib.SOURCE_REMOVE
        self._location_request_manual = bool(user_initiated)
        status, reason = system_location_status(Gio, Geoclue is not None)
        if status != 'try':
            self.notify(reason)
            self._suggest_ip_location(reason, user_initiated=user_initiated)
            return GLib.SOURCE_REMOVE
        if self.location_request is not None:
            return GLib.SOURCE_REMOVE
        self.notify(_('Trying to get location from GeoClue…'))
        try:
            # GeoClue é uma API freedesktop.org, não uma API específica do GNOME.
            cancellable = Gio.Cancellable()
            self.location_request = cancellable
            Geoclue.Simple.new(
                APP_ID, Geoclue.AccuracyLevel.CITY, cancellable,
                lambda source, result, *_: self._location_ready(source, result, cancellable), None)
            # Se o serviço não responde, o mapa continua útil e a opção por IP é oferecida.
            self._geo_timeout_id = GLib.timeout_add_seconds(18, self._geoclue_timed_out, cancellable)
        except Exception as exc:
            self.location_request = None
            self.notify(_('System location unavailable: {value0}').format(value0=exc))
            self._suggest_ip_location(_('Could not use system location service.'),
                                      user_initiated=self._location_request_manual)
        return GLib.SOURCE_REMOVE

    def _geoclue_timed_out(self, cancellable):
        self._geo_timeout_id = 0
        if self.location_request is cancellable:
            self.location_request = None
            cancellable.cancel()
            self.notify(_('System location did not respond.'))
            self._suggest_ip_location(_('System location did not respond within 18 seconds.'),
                                      user_initiated=self._location_request_manual)
        return GLib.SOURCE_REMOVE

    def _location_ready(self, source, result, cancellable):
        if self.location_request is not cancellable:
            # Um pedido anterior expirou ou foi cancelado; ignora resposta atrasada.
            return
        self.location_request = None
        if self._geo_timeout_id:
            GLib.source_remove(self._geo_timeout_id)
            self._geo_timeout_id = 0
        try:
            clue = Geoclue.Simple.new_finish(result)
            loc = clue.get_location()
            if loc is None:
                raise RuntimeError(_('No positions returned'))
            lat, lon = float(loc.get_latitude()), float(loc.get_longitude())
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(_('Invalid coordinates'))
            self._clue = clue  # mantém o cliente ativo durante o uso
            self._last_system_fix = (lat, lon)
            self.move_to(lat, lon, _('My location (GeoClue)'), 10, animated=True)
            self._set_my_position(lat, lon)
            self.notify(_('Location found. The map has been centered.'))
        except Exception as exc:
            self.notify(_('Could not get system location: {value0}').format(value0=exc))
            self._suggest_ip_location(_('Location service could not determine your position.'),
                                      user_initiated=self._location_request_manual)
            # A preferência de privacidade é respeitada: IP somente com confirmação.

    def _set_my_position(self, lat, lon):
        self._last_location_fix = (lat, lon)
        self.my_location_layer.remove_all()
        m = Shumate.Marker.new()
        m.set_location(lat, lon)
        mark = Gtk.Image.new_from_icon_name('find-location-symbolic')
        mark.set_pixel_size(22)
        mark.add_css_class('my-location-marker')
        m.set_child(mark)
        self.my_location_layer.add_marker(m)
        self._my_marker = m
        # The PiP also recenters after a *user-initiated* GeoClue/IP fix.
        pip = getattr(self.get_application(), 'pip_window', None)
        if pip is not None and pip.get_visible():
            pip.recenter_location(lat, lon)


class AeroScopeApp(Adw.Application):
    def __init__(self, demo=False, background_start=False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.demo = demo
        self._starting_background = bool(background_start) and not demo
        self.window = None
        self.pip_window = None
        self._last_main_monitor = None
        self.tray = None
        self._quitting = False
        self._background_active = False
        self._held_open = False
        self._tray_warning_accepted = False
        self._pip_sync_source = 0
        for name, callback in (
            ('preferences', self._prefs), ('support-maps', self._support_maps),
            ('monitor', self._monitor), ('global-alerts', self._global_alerts),
            ('show', self._show), ('hide', self._hide), ('pip', self._pip),
            ('toggle-dashboard', self._toggle_dashboard),
            ('location-ip', self._ip_location),
            ('shortcuts', self._shortcuts),
            ('about', self._about), ('quit', self._quit),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.add_action(action)
        self._visual_action_to_setting = {
            'toggle-tower': 'tower', 'toggle-clock': 'clock_ring',
            'toggle-sweep': 'tower_sweep',
            'toggle-weather-metar': 'weather_metar',
            'toggle-weather-sigmet': 'weather_sigmet',
        }
        initial_settings = load()
        for action_name, key in self._visual_action_to_setting.items():
            action = Gio.SimpleAction.new_stateful(
                action_name, None, GLib.Variant.new_boolean(bool(initial_settings[key])))
            action.connect('change-state', self._visual_option_changed, key)
            self.add_action(action)
        # String-valued (radio) action: one entry selected at a time.
        marker_label_action = Gio.SimpleAction.new_stateful(
            'marker-label', GLib.VariantType.new('s'),
            GLib.Variant.new_string(initial_settings['marker_label']))
        marker_label_action.connect('change-state', self._marker_label_changed)
        self.add_action(marker_label_action)
        sweep_action = self.lookup_action('toggle-sweep')
        if sweep_action is not None:
            sweep_action.set_enabled(bool(initial_settings['tower']))
        self.set_accels_for_action('app.toggle-dashboard', ['F11'])
        self.set_accels_for_action('app.shortcuts', ['F1'])
        self.set_accels_for_action('app.preferences', ['<Alt>comma'])
        self.set_accels_for_action('app.quit', ['<Alt>q'])

    def _shortcuts(self, *_args):
        if self.window is not None:
            from .keyboard_shortcuts_window import show_shortcuts
            show_shortcuts(self.window)

    def _toggle_dashboard(self, *_args):
        if self.window is not None:
            self.show_main_window()
            self.window.toggle_dashboard_mode()

    def _start_tray(self):
        if self.tray is not None:
            return
        from .status_tray import StatusTray
        self.tray = StatusTray(self)
        self.tray.start()

    def _ensure_background_hold(self):
        if not self._held_open:
            self.hold()  # Keep GLib timers and network callbacks alive with no mapped windows.
            self._held_open = True
        self._background_active = True

    def _end_background_hold(self):
        self._background_active = False
        if self._held_open:
            self.release()
            self._held_open = False

    def _hide_background(self):
        if not self.window:
            return
        self._ensure_background_hold()
        self.window._persist_map_view()
        self.window.hide()

    def _show(self, *_):
        self.show_main_window()

    def show_main_window(self):
        if self.window is not None:
            self.window._regional_tracking_started = True
        if self.pip_window is not None:
            if self.pip_window.get_visible():
                self.pip_window.commit_view()
            self.pip_window.hide()
        self._end_background_hold()
        if self.window is not None:
            self.window.present()
            self.window._sync_regional_cadence()
            self.window._refresh_visible_alerts()

    def _pip(self, *_):
        self.show_pip()

    def _pip_source_monitor(self):
        """Capture the screen *before* hiding the main window.

        This is determined from the actual GDK surface's overlap with all
        connected displays, not from primary monitor or pointer location.
        A tray action reuses the last recorded monitor if the main window is
        currently hidden.
        """
        if self.window is not None and self.window.get_mapped():
            surface = self.window.get_surface()
            if surface is not None:
                try:
                    display = surface.get_display()
                    monitor = display.get_monitor_at_surface(surface)
                    if monitor is not None:
                        self._last_main_monitor = monitor
                except (AttributeError, RuntimeError, TypeError) as exc:
                    logging.getLogger('aeroscope.pip').debug(
                        _('Could not identify primary monitor: %s'), exc)
        if self._last_main_monitor is not None:
            if (not hasattr(self._last_main_monitor, 'is_valid')
                    or self._last_main_monitor.is_valid()):
                return self._last_main_monitor
        # First invocation from tray after a login-only background launch:
        # no previous window was on-screen. Use the first connected monitor.
        if self.window is not None and self.window.get_display() is not None:
            model = self.window.get_display().get_monitors()
            if model.get_n_items():
                return model.get_item(0)
        return None

    def show_pip(self):
        if self.window is None:
            return
        source_monitor = self._pip_source_monitor()
        self.window._regional_tracking_started = True
        if self.pip_window is None:
            from .mini_map import MiniMapWindow
            self.pip_window = MiniMapWindow(self, self.window)
        self._ensure_background_hold()
        self.window._persist_map_view()
        self.pip_window.set_source_monitor(source_monitor)
        self.window.hide()
        self.pip_window.sync_initial_view()
        self.pip_window.present()
        self.window._sync_regional_cadence()
        if not self._pip_sync_source:
            self._pip_sync_source = GLib.timeout_add(170, self._pip_sync_tick)

    def _pip_sync_tick(self):
        if self._quitting or not self.pip_window or not self.pip_window.get_visible():
            self._pip_sync_source = 0
            return GLib.SOURCE_REMOVE
        self.pip_window.sync_aircraft()
        return GLib.SOURCE_CONTINUE

    def _hide(self, *_):
        if self.pip_window is not None:
            if self.pip_window.get_visible():
                self.pip_window.commit_view()
            self.pip_window.hide()
        if self.tray and self.tray.available:
            self._hide_background()
        else:
            self._warn_no_tray()

    def handle_window_close(self):
        if self._quitting:
            return False
        state = self.window.settings
        mode = close_behavior(background_enabled=state['background_on_close'],
                              pip_enabled=state['close_to_pip'],
                              indicator_available=bool(self.tray and self.tray.available),
                              warning_accepted=self._tray_warning_accepted)
        if mode == 'quit':
            self._really_quit()
        elif mode == 'pip':
            self.show_pip()
        elif mode == 'hide':
            self._hide_background()
        else:
            self._warn_no_tray()
        return True  # We decide explicitly whether to hide or exit.

    def _warn_no_tray(self):
        if self.window is None:
            return
        dialog = Adw.MessageDialog.new(
            self.window, _('System tray icon unavailable'),
            _('AeroScope can continue monitoring, but your desktop environment does not show a tray icon. You can reopen the app from the application list. Alternatively, open the mini-map or quit.'))
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('background', _('Continue without tray icon'))
        dialog.add_response('pip', _('Mini-map'))
        dialog.add_response('quit', _('Quit'))
        dialog.set_response_appearance('quit', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        def response(_dlg, choice):
            if choice == 'background':
                self._tray_warning_accepted = True
                self._hide_background()
            elif choice == 'pip':
                self.show_pip()
            elif choice == 'quit':
                self._really_quit()
        dialog.connect('response', response)
        dialog.present()

    def _really_quit(self):
        self._quitting = True
        if self.window is not None:
            self.window._persist_map_view()
        if self.tray is not None:
            self.tray.stop()
        if self.pip_window is not None:
            self.pip_window.hide()
        self._end_background_hold()
        self.quit()

    def _visual_option_changed(self, action, value, key):
        if key == 'tower_sweep' and not (self.window and self.window.settings.get('tower')):
            return  # a disabled menu action must never switch on the beam
        enabled = value.get_boolean()
        if self.window is not None:
            self.window._change_setting(key, enabled)
        action.set_state(GLib.Variant.new_boolean(enabled))

    def _marker_label_changed(self, action, value):
        mode = value.get_string()
        if mode not in VALID_MODES:
            return
        if self.window is not None:
            self.window._change_setting('marker_label', mode)
        action.set_state(GLib.Variant.new_string(mode))

    def sync_visual_action(self, key, enabled):
        if key == 'marker_label':
            action = self.lookup_action('marker-label')
            if action is not None:
                action.set_state(GLib.Variant.new_string(enabled))
            return
        if key == 'tower':
            sweep = self.lookup_action('toggle-sweep')
            if sweep is not None:
                sweep.set_enabled(bool(enabled))
        for action_name, setting_key in self._visual_action_to_setting.items():
            if key == setting_key:
                action = self.lookup_action(action_name)
                if action is not None:
                    action.set_state(GLib.Variant.new_boolean(bool(enabled)))
                return

    def _monitor(self, *_):
        if self.window:
            self.window.show_monitor('favorites')

    def _global_alerts(self, *_):
        if self.window:
            self.window.show_monitor('emergencies')

    def _ip_location(self, *_):
        if self.window is not None:
            self.window.confirm_ip_location()

    def _prefs(self, *_):
        if self.window:
            self.window.show_preferences()

    def _support_maps(self, *_):
        # Explicit user action. Map sources continue to show mandatory credit
        # inside Libshumate; donations are optional and never requested in UI.
        Gio.AppInfo.launch_default_for_uri('https://openmaps.fr/donate', None)

    def _about(self, *_args):
        if not self.window:
            return
        dialog = Adw.AboutWindow(
            transient_for=self.window,
            application_name='AeroScope', application_icon=APP_ID,
            developer_name='Eduardo Henrique Teixeira', version=VERSION,
            comments=_('Community aircraft radar for Linux.\nData must not be used for aeronautical navigation or flight safety decisions.'),
            website=GITHUB, issue_url=GITHUB + '/issues',
            license_type=Gtk.License.MIT_X11,
        )
        dialog.add_credit_section(_('Data and maps'), [
            _('ADSB.lol — current positions (ODbL)'),
            _('ADSB.aero — archived history'),
            'Planespotters.net — fotografias e autores',
            'NOAA Aviation Weather Center — METAR / SIGMET (aviationweather.gov)',
            '© OpenStreetMap contributors',
            'OpenTopoMap-R / OpenHikingMap — openmaps.fr',
        ])
        dialog.present()

    def _quit(self, *_):
        self._really_quit()

    def _autostart_tray_check(self):
        # GNOME may not expose StatusNotifierItem unless an extension is
        # installed. Never leave an invisible, unrecoverable autostart process.
        if not self._quitting and not (self.tray and self.tray.available):
            logging.getLogger('aeroscope.tray').warning(
                _('System tray missing at startup: opening regular window'))
            self.show_main_window()
        return GLib.SOURCE_REMOVE

    def do_activate(self):
        if self.window is None:
            silent = self._starting_background
            self.window = RadarWindow(self, demo=self.demo)
            self._start_tray()
            if silent:
                self._ensure_background_hold()
                self._starting_background = False
                GLib.timeout_add(3500, self._autostart_tray_check)
                return
        self.show_main_window()


def main():
    configure_logging(debug=('--debug' in sys.argv))
    PHOTO_LOG.info(_('Photo diagnostics started. For details use: aeroscope --debug'))
    demo = '--demo' in sys.argv
    background_start = '--background' in sys.argv
    app = AeroScopeApp(demo=demo, background_start=background_start)
    app.run([sys.argv[0]])


if __name__ == '__main__':
    main()
