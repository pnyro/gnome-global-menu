"""org.gnome.GlobalMenu D-Bus service: routes the extension's requests to
menu sources (tiers) and emits update signals."""

from __future__ import annotations

import logging

from gi.repository import Gio, GLib

from .model import EMPTY_BAR_JSON, MenuBar, children_to_json
from .sources import Source, WindowInfo
from .sources.atspi import AtspiSource
from .sources.registrar import RegistrarSource

log = logging.getLogger(__name__)

BUS_NAME = "org.gnome.GlobalMenu"
OBJECT_PATH = "/org/gnome/GlobalMenu"
IFACE = "org.gnome.GlobalMenu"
VERSION = 1

INTROSPECTION_XML = """
<node>
  <interface name="org.gnome.GlobalMenu">
    <property name="Version" type="u" access="read"/>
    <method name="SetActiveWindow">
      <arg type="a{sv}" name="info" direction="in"/>
    </method>
    <method name="GetMenuBar">
      <arg type="s" name="menubar_json" direction="out"/>
    </method>
    <method name="GetChildren">
      <arg type="s" name="node_id" direction="in"/>
      <arg type="s" name="children_json" direction="out"/>
    </method>
    <method name="Activate">
      <arg type="u" name="generation" direction="in"/>
      <arg type="s" name="node_id" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="Opened">
      <arg type="s" name="node_id" direction="in"/>
    </method>
    <method name="Closed">
      <arg type="s" name="node_id" direction="in"/>
    </method>
    <method name="GetDiagnostics">
      <arg type="a{sv}" name="info" direction="out"/>
    </method>
    <signal name="MenuBarChanged">
      <arg type="u" name="generation"/>
    </signal>
    <signal name="MenuUpdated">
      <arg type="u" name="generation"/>
      <arg type="s" name="node_id"/>
    </signal>
  </interface>
</node>
"""


class GlobalMenuService:
    def __init__(self, connection: Gio.DBusConnection):
        self._connection = connection
        # Tier order: registrar (dbusmenu) beats AT-SPI for windows it knows.
        self._registrar = RegistrarSource(
            connection, on_menus_changed=self._reclaim_active
        )
        self._sources: list[Source] = [self._registrar, AtspiSource()]
        self._active: Source | None = None
        self._bar: MenuBar | None = None
        self._window: WindowInfo | None = None
        self._focus_count = 0

        node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self._registration = connection.register_object(
            OBJECT_PATH,
            node_info.interfaces[0],
            self._on_method_call,
            self._on_get_property,
            None,
        )

    def unregister(self):
        self._registrar.shutdown()
        if self._registration:
            self._connection.unregister_object(self._registration)
            self._registration = 0

    # -- dispatch -----------------------------------------------------------

    def _on_method_call(
        self, _conn, sender, _path, _iface, method, params, invocation
    ):
        try:
            handler = getattr(self, f"_do_{method}", None)
            if handler is None:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(),
                    Gio.DBusError.UNKNOWN_METHOD,
                    f"No such method {method}",
                )
                return
            handler(params, invocation)
        except Exception as e:
            log.exception("method %s failed", method)
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED, str(e)
            )

    def _on_get_property(self, _conn, _sender, _path, _iface, prop):
        if prop == "Version":
            return GLib.Variant("u", VERSION)
        return None

    def _emit(self, signal: str, variant: GLib.Variant):
        self._connection.emit_signal(None, OBJECT_PATH, IFACE, signal, variant)

    # -- methods ------------------------------------------------------------

    def _do_SetActiveWindow(self, params, invocation):
        (info,) = params.unpack()
        self._focus_count += 1
        window = WindowInfo.from_dict(info)
        log.debug("SetActiveWindow: %r", window)
        self._window = window
        self._update_bar()
        invocation.return_value(None)

    def _update_bar(self):
        window = self._window
        bar = None
        source = None
        if window is not None and window.pid > 0:
            for candidate in self._sources:
                bar = candidate.claim(window)
                if bar is not None:
                    source = candidate
                    break

        self._bar = bar
        self._active = source
        if bar is not None and window is not None:
            log.info(
                "menubar for %s (pid %d) via %s: %d menus",
                window.app_id or window.title,
                window.pid,
                source.name,
                len(bar.menus),
            )
        self._emit(
            "MenuBarChanged",
            GLib.Variant("(u)", (bar.generation if bar else 0,)),
        )

    def _reclaim_active(self):
        """A source's coverage changed (window (un)registered, layout update):
        re-run tier arbitration for the current window."""
        if self._window is not None:
            self._update_bar()

    def _do_GetMenuBar(self, _params, invocation):
        json_str = self._bar.to_json() if self._bar else EMPTY_BAR_JSON
        invocation.return_value(GLib.Variant("(s)", (json_str,)))

    def _do_GetChildren(self, params, invocation):
        (node_id,) = params.unpack()
        children = self._active.get_children(node_id) if self._active else None
        gen = self._bar.generation if self._bar else 0
        json_str = children_to_json(gen, children or [])
        invocation.return_value(GLib.Variant("(s)", (json_str,)))

    def _do_Activate(self, params, invocation):
        generation, node_id = params.unpack()
        ok = self._active.activate(generation, node_id) if self._active else False
        invocation.return_value(GLib.Variant("(b)", (ok,)))

    def _do_Opened(self, params, invocation):
        (node_id,) = params.unpack()
        if self._active:
            self._active.opened(node_id)
        invocation.return_value(None)

    def _do_Closed(self, params, invocation):
        (node_id,) = params.unpack()
        if self._active:
            self._active.closed(node_id)
        invocation.return_value(None)

    def _do_GetDiagnostics(self, _params, invocation):
        atspi = self._sources[-1]
        diag = {
            "version": GLib.Variant("u", VERSION),
            "focus_changes": GLib.Variant("u", self._focus_count),
            "active_source": GLib.Variant("s", self._active.name if self._active else ""),
            "active_pid": GLib.Variant("i", self._window.pid if self._window else 0),
            "generation": GLib.Variant("u", self._bar.generation if self._bar else 0),
            "last_claim_ms": GLib.Variant(
                "d", getattr(atspi, "last_claim_ms", 0.0)
            ),
            "registrar_windows": GLib.Variant("u", self._registrar.window_count),
        }
        invocation.return_value(GLib.Variant("(a{sv})", (diag,)))
