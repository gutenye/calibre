#!/usr/bin/env python
# vim:fileencoding=utf-8
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2014, Kovid Goyal <kovid at kovidgoyal.net>'

import os, sys

import dbus
from PyQt5.Qt import (
    QApplication, QObject, pyqtSignal, Qt, QPoint)

from calibre.utils.dbus_service import Object, method as dbus_method, BusName, dbus_property, signal as dbus_signal

def log(*args, **kw):
    kw['file'] = sys.stderr
    print('StatusNotifier:', *args, **kw)
    kw['file'].flush()

class Factory(QObject):

    SERVICE = "org.kde.StatusNotifierWatcher"
    PATH    = "/StatusNotifierWatcher"
    IFACE   = "org.kde.StatusNotifierWatcher"

    available_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        self.count = 0
        self.items = []
        self.is_available = False
        self._bus = None
        self.connect_to_snw()

    @property
    def bus(self):
        if self._bus is None:
            self._bus = dbus.SessionBus()
        return self._bus

    def bus_disconnected(self, conn):
        self._bus = None

    def init_bus(self):
        bus = self.bus
        bus.call_on_disconnection(self.bus_disconnected)
        bus.watch_name_owner(self.SERVICE, self.owner_changed)
        self.connect_to_snw()

    def owner_changed(self, new_owner):
        old = self.is_available
        if new_owner:
            self.connect_to_snw()
        else:
            self.is_available = False
        if old != self.is_available:
            self.available_changed.emit(self.is_available)

    def connect_to_snw(self):
        self.is_available = False
        try:
            self.bus.add_signal_receiver(self.host_registered, 'StatusNotifierHostRegistered', self.IFACE, self.SERVICE, self.PATH)
        except dbus.DBusException as err:
            log('Failed to connect to StatusNotifierHostRegistered, with error:', str(err))

        self.update_availability()
        if self.is_available:
            for item in self.items:
                self.register(item)

    def update_availability(self):
        try:
            self.is_available = bool(self.bus.call_blocking(
                self.SERVICE, self.PATH, dbus.PROPERTIES_IFACE, 'Get', 'ss', (self.IFACE, 'IsStatusNotifierHostRegistered'), timeout=0.1))
        except dbus.DBusException as err:
            self.is_available = False
            log('Failed to get StatusNotifier host availability with error:', str(err))

    def host_registered(self, *args):
        if not self.is_available:
            self.is_available = True
            self.available_changed.emit(self.is_available)

    def create_indicator(self, **kw):
        if not self.is_available:
            raise RuntimeError('StatusNotifier services are not available on this system')
        self.count += 1
        kw['bus'] = self.bus
        item = StatusNotifierItem(self.count, **kw)
        self.items.append(item)
        item.destroyed.connect(self.items.remove)
        self.register(item)

    def register(self, item):
        self.bus.call_blocking(
            self.SERVICE, self.PATH, self.IFACE, 'RegisterStatusNotifierItem', 's', (item.dbus.name,), timeout=0.1)

class StatusNotifierItem(QObject):

    IFACE = 'org.kde.StatusNotifierItem'
    NewTitle = pyqtSignal()
    NewIcon = pyqtSignal()
    NewAttentionIcon = pyqtSignal()
    NewOverlayIcon = pyqtSignal()
    NewToolTip = pyqtSignal()
    NewStatus = pyqtSignal(str)
    activated = pyqtSignal()
    show_menu = pyqtSignal(int, int)

    def __init__(self, num, **kw):
        QObject.__init__(self, parent=kw.get('parent'))
        self.is_visible = True
        self.show_menu.connect(self._show_menu, type=Qt.QueuedConnection)
        kw['num'] = num
        self.dbus = StatusNotifierItemAPI(self, **kw)

    def _show_menu(self, x, y):
        m = self.contextMenu()
        if m is not None:
            m.exec_(QPoint(x, y))

    def isVisible(self):
        return self.is_visible

    def setVisible(self, visible):
        if self.is_visible != visible:
            self.is_visible = visible
            self.NewStatus.emit(self.dbus.Status)

    def show(self):
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

class StatusNotifierItemAPI(Object):

    IFACE = 'org.kde.StatusNotifierItem'

    def __init__(self, notifier, **kw):
        self.notifier = notifier
        bus = kw.get('bus')
        if bus is None:
            bus = dbus.SessionBus()
        self.name = '%s-%s-%s' % (self.IFACE, os.getpid(), kw.get('num', 1))
        self.dbus_name = BusName(self.name, bus=bus, do_not_queue=True)
        self.app_id = kw.get('app_id', QApplication.instance().applicationName()) or 'unknown_application'
        self.category = kw.get('category', 'ApplicationStatus')
        self.title = kw.get('title', self.app_id)
        Object.__init__(self, bus, '/' + self.IFACE.split('.')[-1])
        for name, val in vars(self.__class__).iteritems():
            if getattr(val, '_dbus_is_signal', False):
                getattr(notifier, name).connect(getattr(self, name))

    @dbus_property(IFACE, signature='s')
    def IconName(self):
        return 'klipper'

    @dbus_property(IFACE, signature='s')
    def IconThemePath(self):
        return ''

    @dbus_property(IFACE, signature='a(iiay)')
    def IconPixmap(self):
        return dbus.Array(signature='(iiay)')

    @dbus_property(IFACE, signature='s')
    def OverlayIconName(self):
        return ''

    @dbus_property(IFACE, signature='a(iiay)')
    def OverlayIconPixmap(self):
        return dbus.Array(signature='(iiay)')

    @dbus_property(IFACE, signature='s')
    def AttentionIconName(self):
        return ''

    @dbus_property(IFACE, signature='a(iiay)')
    def AttentionIconPixmap(self):
        return dbus.Array(signature='(iiay)')

    @dbus_property(IFACE, signature='s')
    def Category(self):
        return self.category

    @dbus_property(IFACE, signature='s')
    def Id(self):
        return self.app_id

    @dbus_property(IFACE, signature='s')
    def Title(self):
        return self.title

    @dbus_property(IFACE, signature='s')
    def Status(self):
        return 'Active' if self.notifier.isVisible() else 'Passive'

    @dbus_property(IFACE, signature='i')
    def WindowId(self):
        return 0

    @dbus_method(IFACE, in_signature='ii', out_signature='')
    def ContextMenu(self, x, y):
        self.notifier.show_menu.emit(x, y)

    @dbus_method(IFACE, in_signature='ii', out_signature='')
    def Activate(self, x, y):
        self.notifier.activated.emit()

    @dbus_method(IFACE, in_signature='ii', out_signature='')
    def SecondaryActivate(self, x, y):
        self.notifier.activated.emit()

    @dbus_method(IFACE, in_signature='is', out_signature='')
    def Scroll(self, delta, orientation):
        pass

    @dbus_signal(IFACE, '')
    def NewTitle(self):
        pass

    @dbus_signal(IFACE, '')
    def NewIcon(self):
        pass

    @dbus_signal(IFACE, '')
    def NewAttentionIcon(self):
        pass

    @dbus_signal(IFACE, '')
    def NewOverlayIcon(self):
        pass

    @dbus_signal(IFACE, '')
    def NewToolTip(self):
        pass

    @dbus_signal(IFACE, 's')
    def NewStatus(self, status):
        pass


_factory = None
def factory():
    global _factory
    if _factory is None:
        _factory = Factory()
    return _factory

def test():
    import signal
    from dbus.mainloop.glib import DBusGMainLoop, threads_init
    DBusGMainLoop(set_as_default=True)
    threads_init()
    app = QApplication([])
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # quit on Ctrl-C
    factory().create_indicator(title='Testing SNI Interface')
    app.exec_()

if __name__ == '__main__':
    test()