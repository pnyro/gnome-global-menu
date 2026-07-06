"""Entry point: python -m globalmenu [-v|--debug]"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from .service import BUS_NAME, GlobalMenuService  # noqa: E402

log = logging.getLogger("globalmenu")


def main() -> int:
    parser = argparse.ArgumentParser(description="GNOME Global Menu daemon")
    parser.add_argument(
        "-v", "--debug", action="store_true", help="verbose logging"
    )
    parser.add_argument(
        "--replace", action="store_true", help="replace a running instance"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    loop = GLib.MainLoop()
    service: dict[str, GlobalMenuService | None] = {"obj": None}

    def on_bus_acquired(connection, name):
        log.info("bus connection acquired, registering %s", name)
        service["obj"] = GlobalMenuService(connection)

    def on_name_lost(_connection, name):
        # Startup failure (name taken) or --replace'd by another instance.
        log.error("lost bus name %s, exiting", name)
        loop.quit()

    flags = Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT
    if args.replace:
        flags |= Gio.BusNameOwnerFlags.REPLACE

    owner_id = Gio.bus_own_name(
        Gio.BusType.SESSION,
        BUS_NAME,
        flags,
        on_bus_acquired,
        lambda *a: log.info("name %s acquired", BUS_NAME),
        on_name_lost,
    )

    def quit_on_signal():
        loop.quit()
        return GLib.SOURCE_REMOVE

    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, quit_on_signal)

    try:
        loop.run()
    finally:
        if service["obj"] is not None:
            service["obj"].unregister()
        Gio.bus_unown_name(owner_id)
        log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
