"""Small elapsed-time indicator for SIGMET advisories with a validity window."""
from __future__ import annotations

from gi.repository import GLib, Gtk

from .i18n import _
from .validity_time import (elapsed_fraction, format_endpoint,
                            validity_window)


class ValidityTimeline(Gtk.Box):
    """A discreet 4px progress track with UTC endpoints; refreshes when mapped."""

    def __init__(self, start, end):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.start, self.end = start, end
        self._timeout_id = 0
        self.add_css_class('sigmet-validity-timeline')

        self.progress = Gtk.ProgressBar()
        self.progress.add_css_class('sigmet-validity-track')
        self.progress.set_show_text(False)
        self.progress.set_hexpand(True)
        self.append(self.progress)

        endpoints = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        endpoints.add_css_class('sigmet-validity-times')
        beginning = Gtk.Label(label=format_endpoint(start), xalign=0)
        beginning.set_tooltip_text(format_endpoint(start, full=True))
        endpoints.append(beginning)
        utc = Gtk.Label(label='UTC')
        utc.set_hexpand(True)
        utc.set_halign(Gtk.Align.CENTER)
        endpoints.append(utc)
        ending = Gtk.Label(label=format_endpoint(end), xalign=1)
        ending.set_tooltip_text(format_endpoint(end, full=True))
        endpoints.append(ending)
        self.append(endpoints)
        self.set_tooltip_text(_('Elapsed portion of the SIGMET validity period, not weather severity.'))
        self._refresh()
        self.connect('map', self._on_map)
        self.connect('unmap', self._on_unmap)

    def _refresh(self):
        fraction = elapsed_fraction(self.start, self.end)
        if fraction is not None:
            self.progress.set_fraction(fraction)

    def _on_map(self, *_args):
        self._refresh()
        if not self._timeout_id:
            self._timeout_id = GLib.timeout_add_seconds(60, self._tick)

    def _on_unmap(self, *_args):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0

    def _tick(self):
        self._refresh()
        return GLib.SOURCE_CONTINUE


def sigmet_timeline(advisory):
    """Return a GTK bar, or None if the provider gave no valid start/end."""
    window = validity_window(getattr(advisory, 'metadata', None))
    return ValidityTimeline(*window) if window else None
