"""Optional X11 'keep above' request for AeroScope's detachable map.

GTK4/Wayland does not expose a portable always-on-top operation. Only the
standard X11 EWMH hint is attempted; compositors are free to ignore it.
"""
from __future__ import annotations
from .i18n import _

import ctypes
import ctypes.util
import logging

LOG = logging.getLogger('aeroscope.pip')


class _XClientData(ctypes.Union):
    _fields_ = [('b', ctypes.c_char * 20), ('s', ctypes.c_short * 10),
                ('l', ctypes.c_long * 5)]


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong),
                ('send_event', ctypes.c_int), ('display', ctypes.c_void_p),
                ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
                ('format', ctypes.c_int), ('data', _XClientData)]


class _XEvent(ctypes.Union):
    _fields_ = [('xclient', _XClientMessageEvent), ('pad', ctypes.c_long * 24)]


def request_x11_above(xid: int, enabled: bool) -> bool:
    """Ask an EWMH window manager to add/remove _NET_WM_STATE_ABOVE.

    Return True if XSendEvent accepted the request, *not* if the window manager
    guaranteed or granted a stacking order. No Gtk3 or additional pip package.
    """
    try:
        library = ctypes.util.find_library('X11')
        if not library or not xid:
            return False
        xlib = ctypes.CDLL(library)
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        xlib.XInternAtom.restype = ctypes.c_ulong
        xlib.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                    ctypes.c_long, ctypes.POINTER(_XEvent)]
        xlib.XSendEvent.restype = ctypes.c_int
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        display = xlib.XOpenDisplay(None)
        if not display:
            return False
        try:
            state = xlib.XInternAtom(display, b'_NET_WM_STATE', 0)
            above = xlib.XInternAtom(display, b'_NET_WM_STATE_ABOVE', 0)
            if not state or not above:
                return False
            evt = _XEvent()
            evt.xclient.type = 33  # ClientMessage
            evt.xclient.serial = 0
            evt.xclient.send_event = 1
            evt.xclient.display = display
            evt.xclient.window = xid
            evt.xclient.message_type = state
            evt.xclient.format = 32
            evt.xclient.data.l[0] = 1 if enabled else 0  # ADD / REMOVE
            evt.xclient.data.l[1] = above
            evt.xclient.data.l[2] = 0
            evt.xclient.data.l[3] = 1  # source: application
            root = xlib.XDefaultRootWindow(display)
            # SubstructureNotifyMask | SubstructureRedirectMask
            success = bool(xlib.XSendEvent(display, root, 0, (1 << 19) | (1 << 20),
                                          ctypes.byref(evt)))
            xlib.XFlush(display)
            return success
        finally:
            xlib.XCloseDisplay(display)
    except (OSError, AttributeError, ValueError, TypeError) as exc:
        LOG.debug('X11 always-on-top request unavailable: %s', exc)
        return False


def request_window_above(window, enabled: bool) -> str:
    """Return requested / unavailable / not-ready; never claim guarantee.

    Uses GdkX11 only when the actual surface is an X11 surface; on Wayland,
    no fake workaround is applied and the WM's own always-above action remains
    available to the user.
    """
    surface = window.get_surface()
    if surface is None:
        return 'not-ready'
    try:
        import gi
        gi.require_version('GdkX11', '4.0')
        from gi.repository import GdkX11
        if not isinstance(surface, GdkX11.X11Surface):
            return 'unavailable'
        return 'requested' if request_x11_above(int(surface.get_xid()), enabled) else 'unavailable'
    except (ImportError, ValueError, TypeError, AttributeError, RuntimeError) as exc:
        LOG.debug('No GdkX11 surface: %s', exc)
        return 'unavailable'


# Window positioning is deliberately X11-only: normal xdg_toplevel windows on
# GNOME/KDE Wayland cannot select their own absolute screen coordinates.
# Keeping this in the existing X11 helper avoids GTK3 dependencies or invoking
# external window-management commands.
def bottom_right_position(monitor_rect, window_size, *, margin=24, workarea=None):
    """Return an (x, y) entirely inside the source monitor, with a margin.

    If the X11 WM publishes a workarea, restrict placement to its intersection
    with the source monitor. The intersection is important for multi-display
    setups where the panel/dock is only on one of the screens.
    """
    mx, my, mw, mh = monitor_rect
    ww, wh = window_size
    if min(mw, mh, ww, wh) <= 0:
        raise ValueError('Invalid monitor/window size')
    left, top, right, bottom = mx, my, mx + mw, my + mh
    if workarea is not None:
        wx, wy, wwidth, wheight = workarea
        xl, yt = max(left, wx), max(top, wy)
        xr, yb = min(right, wx + wwidth), min(bottom, wy + wheight)
        if xr > xl and yb > yt:
            left, top, right, bottom = xl, yt, xr, yb
    # Do not let a large PiP or unusually small monitor cause negative margins.
    x = max(left, right - max(0, margin) - ww)
    y = max(top, bottom - max(0, margin) - wh)
    return int(x), int(y)


def _x11_workarea():
    """Read the EWMH workarea for the current desktop, if exposed by the WM."""
    try:
        library = ctypes.util.find_library('X11')
        if not library:
            return None
        xlib = ctypes.CDLL(library)
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        xlib.XInternAtom.restype = ctypes.c_ulong
        xlib.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
            ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))]
        xlib.XGetWindowProperty.restype = ctypes.c_int
        xlib.XFree.argtypes = [ctypes.c_void_p]
        xlib.XFree.restype = ctypes.c_int
        dpy = xlib.XOpenDisplay(None)
        if not dpy:
            return None
        try:
            root = xlib.XDefaultRootWindow(dpy)
            def prop(name, count):
                atom = xlib.XInternAtom(dpy, name, 1)
                if not atom:
                    return []
                actual_type = ctypes.c_ulong()
                actual_format = ctypes.c_int()
                nitems = ctypes.c_ulong()
                bytes_after = ctypes.c_ulong()
                data = ctypes.POINTER(ctypes.c_ubyte)()
                result = xlib.XGetWindowProperty(
                    dpy, root, atom, 0, count, 0, 0,
                    ctypes.byref(actual_type), ctypes.byref(actual_format),
                    ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(data))
                try:
                    if result != 0 or actual_format.value != 32 or not data:
                        return []
                    values = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
                    return [int(values[i]) for i in range(nitems.value)]
                finally:
                    if data:
                        xlib.XFree(ctypes.cast(data, ctypes.c_void_p))
            desktop = prop(b'_NET_CURRENT_DESKTOP', 1)
            areas = prop(b'_NET_WORKAREA', 64)
            if len(areas) < 4:
                return None
            index = (desktop[0] if desktop else 0) * 4
            if index + 4 > len(areas):
                index = 0
            return tuple(areas[index:index + 4])
        finally:
            xlib.XCloseDisplay(dpy)
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        LOG.debug('X11 workarea unavailable: %s', exc)
        return None


def request_x11_position(xid: int, x: int, y: int) -> bool:
    """Ask the X11 server to move a window; the WM may adjust the result."""
    if not xid:
        return False
    try:
        library = ctypes.util.find_library('X11')
        if not library:
            return False
        xlib = ctypes.CDLL(library)
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                    ctypes.c_int, ctypes.c_int]
        xlib.XMoveWindow.restype = ctypes.c_int
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        dpy = xlib.XOpenDisplay(None)
        if not dpy:
            return False
        try:
            xlib.XMoveWindow(dpy, int(xid), int(x), int(y))
            xlib.XFlush(dpy)
            return True
        finally:
            xlib.XCloseDisplay(dpy)
    except (OSError, AttributeError, ValueError, TypeError) as exc:
        LOG.debug('Could not position X11 mini-map: %s', exc)
        return False


def request_window_corner(window, monitor, *, margin=24):
    """Bottom-right of the MAIN window's monitor, using its X11 surface.

    Return 'requested', 'unavailable' or 'not-ready'; never claim Wayland
    placement succeeded when the compositor decides its location instead.
    """
    if monitor is None:
        return 'unavailable'
    surface = window.get_surface()
    if surface is None:
        return 'not-ready'
    try:
        import gi
        gi.require_version('GdkX11', '4.0')
        from gi.repository import GdkX11
        if not isinstance(surface, GdkX11.X11Surface):
            return 'unavailable'
        geo = monitor.get_geometry()
        if hasattr(monitor, 'is_valid') and not monitor.is_valid():
            return 'unavailable'
        # GDK monitor dimensions and GTK widget allocations are application
        # pixels. On X11 the root window uses physical pixels.
        scale = max(1, int(surface.get_scale_factor()))
        rect = (geo.x * scale, geo.y * scale, geo.width * scale, geo.height * scale)
        size = (window.get_width() * scale, window.get_height() * scale)
        if size[0] <= 0 or size[1] <= 0:
            return 'not-ready'
        coords = bottom_right_position(rect, size, margin=margin * scale,
                                       workarea=_x11_workarea())
        if request_x11_position(int(surface.get_xid()), *coords):
            LOG.info(_('Mini-map: requested X11 position %s, monitor %s'), coords, rect)
            return 'requested'
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as exc:
        LOG.debug('Mini-map X11 placement unavailable: %s', exc)
    return 'unavailable'
