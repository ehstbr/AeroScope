"""GTK4-compatible StatusNotifierItem + DBusMenu, backed by GLib/Gio only.

StatusNotifierItem is supported by KDE and opt-in GNOME Shell tray extensions.
No Gtk3 / libappindicator process is loaded into a Gtk4 application.
"""
from __future__ import annotations
from .i18n import _

import logging
from gi.repository import Gio, GLib

LOG = logging.getLogger('aeroscope.tray')

ITEM_XML = '''<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="WindowId" type="u" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <signal name="NewIcon"/>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
</node>'''

MENU_XML = '''<node><interface name="com.canonical.dbusmenu">
 <method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/>
  <arg type="as" direction="in"/><arg type="u" direction="out"/>
  <arg type="(ia{sv}av)" direction="out"/></method>
 <method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/>
  <arg type="a(ia{sv})" direction="out"/></method>
 <method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/>
  <arg type="v" direction="out"/></method>
 <method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/>
  <arg type="v" direction="in"/><arg type="u" direction="in"/></method>
 <method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
 <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
 <method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/>
  <arg type="ai" direction="out"/></method>
 <property name="Version" type="u" access="read"/>
 <property name="Status" type="s" access="read"/>
 <property name="TextDirection" type="s" access="read"/>
 <property name="IconThemePath" type="s" access="read"/>
 <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
</interface></node>'''


class StatusTray:
    ITEM_PATH = '/StatusNotifierItem'
    MENU_PATH = '/StatusNotifierMenu'
    ITEMS = ((1, _('Open AeroScope'), 'show'),
             (2, _('Show mini-map'), 'pip'),
             (3, '', 'separator'),
             (4, _('Quit AeroScope'), 'quit'))

    def __init__(self, app):
        self.app = app
        self.bus = None
        self.available = False
        self._item_id = 0
        self._menu_id = 0
        self._watch_id = 0
        self._bus_name = None
        self._item_node = None
        self._menu_node = None

    def start(self):
        try:
            self._watch_id = Gio.bus_watch_name(
                Gio.BusType.SESSION, 'org.kde.StatusNotifierWatcher',
                Gio.BusNameWatcherFlags.NONE, self._watcher_appeared,
                self._watcher_vanished)
        except (GLib.Error, RuntimeError, AttributeError) as exc:
            LOG.info(_('System tray unavailable: %s'), exc)

    def _watcher_appeared(self, connection, name, owner):
        if self.available:
            return
        self.bus = connection
        try:
            from .settings import APP_ID
            self._bus_name = connection.get_unique_name()
            self._item_node = Gio.DBusNodeInfo.new_for_xml(ITEM_XML)
            self._menu_node = Gio.DBusNodeInfo.new_for_xml(MENU_XML)
            item_info = self._item_node.interfaces[0]
            menu_info = self._menu_node.interfaces[0]
            self._item_id = connection.register_object(self.ITEM_PATH, item_info,
                                                       self._method_item, self._property_item, None)
            self._menu_id = connection.register_object(self.MENU_PATH, menu_info,
                                                       self._method_menu, self._property_menu, None)
            connection.call_sync('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
                                 'org.kde.StatusNotifierWatcher', 'RegisterStatusNotifierItem',
                                 GLib.Variant('(s)', (self._bus_name,)), None,
                                 Gio.DBusCallFlags.NONE, 1300, None)
            self.available = True
            LOG.info(_('StatusNotifier icon registered with desktop (%s)'), owner)
        except Exception as exc:
            LOG.warning(_('Could not create system tray: %s'), exc)
            self._unregister()

    def _watcher_vanished(self, connection, name):
        self.available = False
        self._unregister()

    def _unregister(self):
        if self.bus:
            for ident in (self._item_id, self._menu_id):
                if ident:
                    try:
                        self.bus.unregister_object(ident)
                    except (GLib.Error, RuntimeError):
                        pass
        self._item_id = 0
        self._menu_id = 0
        self.available = False

    def stop(self):
        if self._watch_id:
            Gio.bus_unwatch_name(self._watch_id)
            self._watch_id = 0
        self._unregister()

    def _property_item(self, connection, sender, path, interface, prop):
        from .settings import APP_ID
        props = {
            'Category': GLib.Variant('s','ApplicationStatus'),
            'Id': GLib.Variant('s',APP_ID),
            'Title': GLib.Variant('s',_('AeroScope · Radar running')),
            'Status': GLib.Variant('s','Active'),
            'IconName': GLib.Variant('s',APP_ID),
            'IconThemePath': GLib.Variant('s','/usr/share/icons/hicolor/scalable/apps'),
            'ItemIsMenu': GLib.Variant('b',False),
            'Menu': GLib.Variant('o',self.MENU_PATH),
            'WindowId': GLib.Variant('u',0),
            'IconPixmap': GLib.Variant('a(iiay)', []),
        }
        return props.get(prop)

    def _property_menu(self, connection, sender, path, interface, prop):
        props = {'Version':GLib.Variant('u',4),
                 'Status':GLib.Variant('s','normal'),
                 'TextDirection':GLib.Variant('s','ltr'),
                 'IconThemePath':GLib.Variant('s','')}
        return props.get(prop)

    def _dispatch(self, action):
        self.app.activate_action(action, None)
        return GLib.SOURCE_REMOVE

    def _method_item(self, connection, sender, path, interface, method, parameters, invocation):
        if method in ('Activate','SecondaryActivate'):
            GLib.idle_add(self._dispatch, 'show' if method == 'Activate' else 'pip')
        invocation.return_value(GLib.Variant('()', ()))

    def _properties_for(self, ident, filter_names=()):
        props = {}
        for item_id, label, action in self.ITEMS:
            if item_id != ident:
                continue
            props = {'label':GLib.Variant('s',label), 'enabled':GLib.Variant('b',True),
                     'visible':GLib.Variant('b',True)}
            if action == 'separator':
                props['type'] = GLib.Variant('s','separator')
            break
        if filter_names:
            props = {key:value for key,value in props.items() if key in filter_names}
        return props

    def _menu_layout(self, parent_id=0, depth=-1, filter_names=()):
        if parent_id != 0:
            return (parent_id, self._properties_for(parent_id, filter_names), [])
        children = []
        if depth != 0:
            for ident, _, _ in self.ITEMS:
                node = (ident, self._properties_for(ident, filter_names), [])
                children.append(GLib.Variant('(ia{sv}av)', node))
        return (0, {}, children)

    def _menu_click(self, ident, event):
        if event != 'clicked':
            return
        for item_id, label, action in self.ITEMS:
            if ident == item_id and action != 'separator':
                GLib.idle_add(self._dispatch, action)
                break

    def _method_menu(self, connection, sender, path, interface, method, parameters, invocation):
        args = parameters.unpack()
        if method == 'GetLayout':
            ident, depth, names = args
            value = GLib.Variant('(u(ia{sv}av))',
                                 (1, self._menu_layout(ident, depth, names)))
        elif method == 'GetGroupProperties':
            ids, names = args
            identifiers = ids or [row[0] for row in self.ITEMS]
            value = GLib.Variant('(a(ia{sv}))',
                                 ([(n, self._properties_for(n, names)) for n in identifiers],))
        elif method == 'GetProperty':
            ident, name = args
            value = GLib.Variant('(v)',(self._properties_for(ident).get(
                name, GLib.Variant('s','')),))
        elif method == 'Event':
            self._menu_click(args[0],args[1]); value = GLib.Variant('()',())
        elif method == 'EventGroup':
            for ident, event, data, stamp in args[0]:
                self._menu_click(ident,event)
            value = GLib.Variant('(ai)', ([],))
        elif method == 'AboutToShow':
            value = GLib.Variant('(b)', (False,))
        elif method == 'AboutToShowGroup':
            value = GLib.Variant('(aiai)', ([],[]))
        else:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod',method)
            return
        invocation.return_value(value)
