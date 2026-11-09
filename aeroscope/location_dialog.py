"""One size-stable, privacy-conscious IP-location prompt for main map and PiP.

Adw.MessageDialog makes its footer responsive to the *parent* window width.
For a three-action consent prompt this changes the button order/layout between
AeroScope's main window and mini-map. A single explicit vertical layout avoids
that visual discrepancy without changing the opt-in geolocation policy.
"""
from __future__ import annotations

from gi.repository import Gtk, Pango


class IpLocationDialog(Gtk.Window):
    """Compact modal with deterministic vertical action order on any desktop."""

    def __init__(self, parent, title: str, explanation: str, actions,
                 on_response, close_response: str = 'later'):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_default_size(372, -1)
        self.add_css_class('ip-location-dialog')
        self._answered = False
        self._callback = on_response
        self._close_response = close_response
        self.connect('close-request', self._closed_by_user)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(content, f'set_margin_{side}')(22)
        self.set_child(content)

        heading = Gtk.Label(label=title)
        heading.add_css_class('title-3')
        heading.set_justify(Gtk.Justification.CENTER)
        heading.set_wrap(True)
        heading.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        heading.set_max_width_chars(37)
        content.append(heading)

        message = Gtk.Label(label=explanation)
        message.set_justify(Gtk.Justification.CENTER)
        message.set_wrap(True)
        message.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        message.set_max_width_chars(39)
        message.set_xalign(.5)
        content.append(message)

        choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        choices.set_margin_top(8)
        content.append(choices)
        for response, caption, primary in actions:
            button = Gtk.Button(label=caption)
            button.set_hexpand(True)
            if primary:
                button.add_css_class('suggested-action')
            button.connect('clicked', lambda _button, key=response: self._answer(key))
            choices.append(button)

    def _answer(self, response: str):
        if self._answered:
            return
        self._answered = True
        self._callback(self, response)
        self.destroy()

    def _closed_by_user(self, *_):
        self._answer(self._close_response)
        return False
