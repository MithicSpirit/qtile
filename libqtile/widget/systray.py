from __future__ import division

from .. import bar, xcbq, window
from . import base

import xcffib
from xcffib.xproto import EventMask, SetMode
import atexit
import struct


class Icon(window._Window):
    _windowMask = EventMask.StructureNotify | \
        EventMask.Exposure

    def __init__(self, win, qtile, systray):
        window._Window.__init__(self, win, qtile)
        self.systray = systray
        self.width = systray.icon_size
        self.height = systray.icon_size

    def handle_ConfigureNotify(self, event):
        icon_size = self.systray.icon_size
        self.updateHints()

        try:
            width = self.hints["min_width"]
            height = self.hints["min_height"]
        except KeyError:
            width = icon_size
            height = icon_size

        if height > icon_size:
            width = width * icon_size // height
            height = icon_size
        if height <= 0:
            width = icon_size
            height = icon_size

        self.width = width
        self.height = height
        self.window.set_attribute(backpixmap=self.systray.drawer.pixmap)
        return False

    def handle_DestroyNotify(self, event):
        wid = event.window
        del(self.qtile.windowMap[wid])
        del(self.systray.icons[wid])
        self.systray.draw()
        return False

    handle_UnmapNotify = handle_DestroyNotify


class TrayWindow(window._Window):
    _windowMask = EventMask.StructureNotify | \
        EventMask.Exposure

    def __init__(self, win, qtile, systray):
        window._Window.__init__(self, win, qtile)
        self.systray = systray

    def handle_ClientMessage(self, event):
        atoms = self.qtile.conn.atoms

        opcode = event.type
        data = event.data.data32
        message = data[1]
        wid = data[2]

        conn = self.qtile.conn.conn
        parent = self.systray.bar.window.window

        # message == 0 corresponds to SYSTEM_TRAY_REQUEST_DOCK
        # TODO: handle system tray messages http://standards.freedesktop.org/systemtray-spec/systemtray-spec-latest.html
        if opcode == atoms['_NET_SYSTEM_TRAY_OPCODE'] and message == 0:
            try:
                w = xcbq.Window(self.qtile.conn, wid)
                icon = Icon(w, self.qtile, self.systray)
                self.systray.icons[wid] = icon
                self.qtile.windowMap[wid] = icon

                # add icon window to the save-set, so it gets reparented
                # to the root window when qtile dies
                conn.core.ChangeSaveSet(SetMode.Insert, wid)

                conn.core.ReparentWindow(wid, parent.wid, 0, 0)
                conn.flush()
                w.map()
            except xcffib.xproto.DrawableError:
                # The icon wasn't ready to be drawn yet... (NetworkManager does
                # this sometimes), so we just forget about it and wait for the
                # next event.
                pass
        return False


class Systray(base._Widget):
    """
        A widget that manage system tray
    """
    defaults = [
        ('icon_size', 20, 'Icon width'),
        ('padding', 5, 'Padding between icons'),
    ]

    def __init__(self, **config):
        base._Widget.__init__(self, bar.CALCULATED, **config)
        self.add_defaults(Systray.defaults)
        self.traywin = None
        self.icons = {}

    def button_press(self, x, y, button):
        pass

    def calculate_width(self):
        width = sum([i.width for i in self.icons.values()])
        width += self.padding * len(self.icons)
        return width

    def _configure(self, qtile, bar):
        base._Widget._configure(self, qtile, bar)
        self.qtile = qtile
        self.bar = bar
        atoms = qtile.conn.atoms
        win = qtile.conn.create_window(-1, -1, 1, 1)
        self.traywin = TrayWindow(win, self.qtile, self)
        qtile.windowMap[win.wid] = self.traywin
        qtile.conn.conn.core.SetSelectionOwner(
            win.wid,
            atoms['_NET_SYSTEM_TRAY_S0'],
            xcffib.CurrentTime
        )
        event = struct.pack(
            'BBHII5I', 33, 32, 0, qtile.root.wid,
            atoms['MANAGER'],
            xcffib.CurrentTime, atoms['_NET_SYSTEM_TRAY_S0'],
            win.wid, 0, 0
        )
        qtile.root.send_event(event, mask=EventMask.StructureNotify)

        # cleanup before exit
        atexit.register(self.cleanup)

    def draw(self):
        self.drawer.clear(self.background or self.bar.background)
        self.drawer.draw(self.offset, self.calculate_width())
        xoffset = self.padding
        for pos, icon in enumerate(self.icons.values()):
            icon.place(
                self.offset + xoffset,
                self.bar.height // 2 - self.icon_size // 2,
                icon.width, self.icon_size,
                0,
                None
            )
            xoffset += icon.width + self.padding

    def cleanup(self):
        atoms = self.qtile.conn.atoms
        self.qtile.conn.conn.core.SetSelectionOwner(
            0,
            atoms['_NET_SYSTEM_TRAY_S0'],
            xcffib.CurrentTime,
        )
        self.traywin.hide()
