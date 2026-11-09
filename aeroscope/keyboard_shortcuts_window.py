"""Simple GTK4 keyboard shortcut reference, without deprecated ShortcutsWindow."""

from .i18n import _
from .keyboard_shortcuts import shortcut_groups

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango


def show_shortcuts(parent):
    existing = getattr(parent, '_shortcut_help_window', None)
    if existing is not None and existing.get_visible():
        existing.present()
        return existing
    win = Gtk.Window(transient_for=parent, modal=False, title=_('Keyboard shortcuts'),
                     default_width=480, default_height=540)
    win.set_hide_on_close(True)
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    win.set_child(root)
    # Gtk.Window already supplies the native titlebar and close button.
    # Adding a HeaderBar inside its content produced a duplicate title row.
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    root.append(scroll)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
    for name in ('start', 'end', 'top', 'bottom'):
        getattr(content, 'set_margin_' + name)(20)
    scroll.set_child(content)
    for title, actions in shortcut_groups():
        group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class('heading')
        group.append(heading)
        for description, accelerator, alternate in actions:
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            label = Gtk.Label(label=description, xalign=0)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            line.append(label)
            # Explicit textual labels remain legible with non-US layouts and
            # include keypad/alternate bindings the compact GTK glyph cannot.
            key = Gtk.Label(label=alternate, xalign=1)
            key.add_css_class('keyboard-shortcut-key')
            key.set_selectable(False)
            line.append(key)
            group.append(line)
        content.append(group)
    note = Gtk.Label(label=_('Use Alt for AeroScope commands. Ctrl+A, Ctrl+C and Ctrl+V remain available for text editing; F1 and F11 work without Alt.'),
                     xalign=0, wrap=True)
    note.add_css_class('dim-label')
    content.append(note)
    parent._shortcut_help_window = win
    win.present()
    return win
