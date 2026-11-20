"""Drive a virtual pointer on the Playwright worker's own GNOME compositor."""

import sys
import time

from gi.repository import Gio, GLib


def main() -> None:
    x, y = (float(value) for value in sys.argv[1:3])
    action = sys.argv[3]
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    interface = "org.gnome.Mutter.RemoteDesktop"
    root = "/org/gnome/Mutter/RemoteDesktop"

    def call(path, name, method, args=None):
        return bus.call_sync(interface, path, name, method, args, None, Gio.DBusCallFlags.NONE, 2000, None)

    session, = call(root, interface, "CreateSession").unpack()

    def send(method, signature, *args):
        call(session, interface + ".Session", method, GLib.Variant(signature, args))

    call(session, interface + ".Session", "Start")
    try:
        if action == "activate":
            # The test compositor can start with its overview visible.
            send("NotifyKeyboardKeysym", "(ub)", 0xFF1B, True)
            send("NotifyKeyboardKeysym", "(ub)", 0xFF1B, False)
            time.sleep(0.35)
        # The virtual monitor has one origin. Moving to its corner lets us
        # specify a screen position without PipeWire/screencast setup.
        send("NotifyPointerMotionRelative", "(dd)", -10000.0, -10000.0)
        time.sleep(0.08)
        send("NotifyPointerMotionRelative", "(dd)", x, y)
        time.sleep(0.12)
        if action in ("activate", "click"):
            send("NotifyPointerButton", "(ib)", 272, True)
            time.sleep(0.03)
            send("NotifyPointerButton", "(ib)", 272, False)
        elif action == "scroll":
            for delta in sys.argv[4:]:
                send("NotifyPointerAxis", "(ddu)", 0.0, float(delta), 0)
                time.sleep(0.015)
            send("NotifyPointerAxis", "(ddu)", 0.0, 0.0, 1)
        time.sleep(0.18)
    finally:
        call(session, interface + ".Session", "Stop")


if __name__ == "__main__":
    main()
