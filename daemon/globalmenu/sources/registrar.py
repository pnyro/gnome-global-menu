"""Tier 2: com.canonical.AppMenu.Registrar + DBusMenu client.

The daemon owns the registrar name; Qt (and libdbusmenu) apps that find it
export their menubar as a com.canonical.dbusmenu object and register it per
window. We track registrations by sender bus name + PID (queried from the
bus daemon), so native-Wayland Qt apps — whose "window ids" are Qt-internal
counters, not X ids — still match the focused window by PID. XWayland apps
match by real X window id first.

Like the AT-SPI tier, this source is lazy: claim() serializes only the
top-level entries (one GetLayout of depth 1); children are fetched fresh on
open, preceded by AboutToShow so dynamic Qt menus populate themselves.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from gi.repository import Gio, GLib

from ..model import (
    TYPE_CHECKBOX,
    TYPE_ITEM,
    TYPE_RADIO,
    TYPE_SEPARATOR,
    TYPE_SUBMENU,
    MenuBar,
    MenuNode,
)
from . import Source, WindowInfo

log = logging.getLogger(__name__)

REGISTRAR_BUS_NAME = "com.canonical.AppMenu.Registrar"
REGISTRAR_PATH = "/com/canonical/AppMenu/Registrar"
DBUSMENU_IFACE = "com.canonical.dbusmenu"

# Per-call timeout talking to the app; a hung app degrades, never blocks us.
CALL_TIMEOUT_MS = 300
# Debounce for change notifications (registrations + layout signals).
NOTIFY_DEBOUNCE_MS = 150

REGISTRAR_XML = """
<node>
  <interface name="com.canonical.AppMenu.Registrar">
    <method name="RegisterWindow">
      <arg type="u" name="windowId" direction="in"/>
      <arg type="o" name="menuObjectPath" direction="in"/>
    </method>
    <method name="UnregisterWindow">
      <arg type="u" name="windowId" direction="in"/>
    </method>
    <method name="GetMenuForWindow">
      <arg type="u" name="windowId" direction="in"/>
      <arg type="s" name="service" direction="out"/>
      <arg type="o" name="menuObjectPath" direction="out"/>
    </method>
    <signal name="WindowRegistered">
      <arg type="u" name="windowId"/>
      <arg type="s" name="service"/>
      <arg type="o" name="menuObjectPath"/>
    </signal>
    <signal name="WindowUnregistered">
      <arg type="u" name="windowId"/>
    </signal>
  </interface>
</node>
"""

# dbusmenu item properties we care about.
ITEM_PROPS = [
    "type",
    "label",
    "enabled",
    "visible",
    "toggle-type",
    "toggle-state",
    "children-display",
    "shortcut",
]

_MOD_NAMES = {"Control", "Ctrl", "Shift", "Alt", "Super", "Meta"}


def _strip_mnemonic(label: str) -> str:
    """dbusmenu labels mark mnemonics with '_' ('__' is a literal '_').
    The renderer does not draw mnemonic underlines yet, so strip them."""
    return label.replace("__", "\x00").replace("_", "").replace("\x00", "_")


def _shortcut_to_accel(shortcut) -> Optional[str]:
    """dbusmenu 'shortcut' is aas, e.g. [["Control","Shift","S"]] →
    '<Control><Shift>s' (GTK accelerator string, first chord only)."""
    if not shortcut or not shortcut[0]:
        return None
    chord = shortcut[0]
    mods, key = chord[:-1], chord[-1]
    accel = "".join(f"<{m}>" for m in mods if m in _MOD_NAMES)
    return accel + (key.lower() if len(key) == 1 else key)


@dataclass
class Registration:
    window_id: int
    sender: str
    path: str
    pid: int
    order: int  # monotonic; newest registration wins PID-based matching


class RegistrarSource(Source):
    """Owns the AppMenu registrar and serves registered DBusMenu menus."""

    name = "dbusmenu"

    def __init__(
        self,
        connection: Gio.DBusConnection,
        on_menus_changed: Optional[Callable[[], None]] = None,
    ):
        self._connection = connection
        self._on_menus_changed = on_menus_changed
        self._registrations: dict[int, Registration] = {}
        self._sender_watches: dict[str, int] = {}
        self._order = 0
        self._notify_id = 0

        # active claim
        self._generation = 0
        self._reg: Optional[Registration] = None
        self._known_ids: set[int] = set()
        self._signal_sub = 0

        node_info = Gio.DBusNodeInfo.new_for_xml(REGISTRAR_XML)
        self._object_id = connection.register_object(
            REGISTRAR_PATH,
            node_info.interfaces[0],
            self._on_method_call,
            None,
            None,
        )
        self._owner_id = Gio.bus_own_name_on_connection(
            connection,
            REGISTRAR_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            lambda *a: log.info("registrar name %s acquired", REGISTRAR_BUS_NAME),
            lambda *a: log.warning(
                "registrar name %s lost (another appmenu service running?)",
                REGISTRAR_BUS_NAME,
            ),
        )

    def shutdown(self):
        self._unsubscribe()
        for watch_id in self._sender_watches.values():
            Gio.bus_unwatch_name(watch_id)
        self._sender_watches.clear()
        if self._notify_id:
            GLib.source_remove(self._notify_id)
            self._notify_id = 0
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0
        if self._object_id:
            self._connection.unregister_object(self._object_id)
            self._object_id = 0

    @property
    def window_count(self) -> int:
        return len(self._registrations)

    # -- registrar D-Bus object --------------------------------------------

    def _on_method_call(self, _conn, sender, _path, _iface, method, params, invocation):
        try:
            if method == "RegisterWindow":
                window_id, menu_path = params.unpack()
                self._register(int(window_id), sender, menu_path)
                invocation.return_value(None)
            elif method == "UnregisterWindow":
                (window_id,) = params.unpack()
                self._unregister(int(window_id), sender)
                invocation.return_value(None)
            elif method == "GetMenuForWindow":
                (window_id,) = params.unpack()
                reg = self._registrations.get(int(window_id))
                if reg is None:
                    invocation.return_error_literal(
                        Gio.dbus_error_quark(),
                        Gio.DBusError.FAILED,
                        f"no menu registered for window {window_id}",
                    )
                else:
                    invocation.return_value(
                        GLib.Variant("(so)", (reg.sender, reg.path))
                    )
            else:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(),
                    Gio.DBusError.UNKNOWN_METHOD,
                    f"No such method {method}",
                )
        except Exception as e:
            log.exception("registrar method %s failed", method)
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED, str(e)
            )

    def _register(self, window_id: int, sender: str, menu_path: str):
        pid = self._pid_of(sender)
        self._order += 1
        self._registrations[window_id] = Registration(
            window_id=window_id, sender=sender, path=menu_path, pid=pid, order=self._order
        )
        log.info(
            "window %d registered by %s (pid %d) at %s",
            window_id, sender, pid, menu_path,
        )
        self._watch_sender(sender)
        self._emit_registrar(
            "WindowRegistered", GLib.Variant("(uso)", (window_id, sender, menu_path))
        )
        self._schedule_notify()

    def _unregister(self, window_id: int, sender: Optional[str]):
        reg = self._registrations.get(window_id)
        if reg is None:
            return
        # Only the registering connection may unregister (sender=None: internal).
        if sender is not None and reg.sender != sender:
            log.warning(
                "unregister of window %d by %s denied (owner %s)",
                window_id, sender, reg.sender,
            )
            return
        del self._registrations[window_id]
        log.info("window %d unregistered", window_id)
        self._emit_registrar("WindowUnregistered", GLib.Variant("(u)", (window_id,)))
        if self._reg is not None and self._reg.window_id == window_id:
            self._reset()
        self._schedule_notify()

    def _emit_registrar(self, signal: str, variant: GLib.Variant):
        try:
            self._connection.emit_signal(
                None, REGISTRAR_PATH, "com.canonical.AppMenu.Registrar", signal, variant
            )
        except Exception:
            log.exception("emitting %s failed", signal)

    def _pid_of(self, sender: str) -> int:
        try:
            result = self._connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "GetConnectionUnixProcessID",
                GLib.Variant("(s)", (sender,)),
                GLib.VariantType("(u)"),
                Gio.DBusCallFlags.NONE,
                CALL_TIMEOUT_MS,
                None,
            )
            return int(result.unpack()[0])
        except Exception:
            log.warning("could not resolve PID of %s", sender, exc_info=True)
            return 0

    def _watch_sender(self, sender: str):
        if sender in self._sender_watches:
            return
        self._sender_watches[sender] = Gio.bus_watch_name_on_connection(
            self._connection,
            sender,
            Gio.BusNameWatcherFlags.NONE,
            None,
            self._on_sender_vanished,
        )

    def _on_sender_vanished(self, _connection, sender: str):
        watch_id = self._sender_watches.pop(sender, None)
        if watch_id is not None:
            Gio.bus_unwatch_name(watch_id)
        gone = [wid for wid, reg in self._registrations.items() if reg.sender == sender]
        for window_id in gone:
            self._unregister(window_id, None)
        if gone:
            log.info("%s vanished, dropped %d window(s)", sender, len(gone))

    def _schedule_notify(self):
        if self._on_menus_changed is None or self._notify_id:
            return

        def fire():
            self._notify_id = 0
            self._on_menus_changed()
            return GLib.SOURCE_REMOVE

        self._notify_id = GLib.timeout_add(NOTIFY_DEBOUNCE_MS, fire)

    # -- Source: claiming ---------------------------------------------------

    def claim(self, window: WindowInfo) -> Optional[MenuBar]:
        reg = self._match(window)
        if reg is None:
            self._reset()
            return None

        menus = self._fetch_children(reg, 0)
        if menus is None:
            # Registered but unreachable/empty: let a lower tier try.
            self._reset()
            return None

        if self._reg is None or (self._reg.sender, self._reg.path) != (reg.sender, reg.path):
            # New menu object: previously served ids belong to the old one.
            self._known_ids = {0} | {
                int(m.id[1:]) for m in menus if m.id.startswith("r")
            }
            self._subscribe(reg)
        self._reg = reg
        self._generation += 1
        return MenuBar(
            source=self.name,
            generation=self._generation,
            app_id=window.app_id,
            menus=[m for m in menus if m.label or m.type == TYPE_SEPARATOR],
        )

    def _match(self, window: WindowInfo) -> Optional[Registration]:
        if window.xid and window.xid in self._registrations:
            return self._registrations[window.xid]
        if window.pid > 0:
            mine = [r for r in self._registrations.values() if r.pid == window.pid]
            if mine:
                return max(mine, key=lambda r: r.order)
        return None

    # -- Source: children / activation --------------------------------------

    def get_children(self, node_id: str) -> Optional[list[MenuNode]]:
        item_id = self._item_id(node_id)
        if item_id is None or self._reg is None:
            return None
        # Dynamic Qt menus fill themselves on AboutToShow; do it synchronously
        # so the following GetLayout sees the populated menu.
        self._about_to_show(item_id)
        return self._fetch_children(self._reg, item_id) or []

    def activate(self, generation: int, node_id: str) -> bool:
        # dbusmenu item ids are stable within the app's menu object, so a
        # known id is safe to activate even if the generation moved on (Qt
        # apps emit layout churn on AboutToShow; the id still means the same
        # item). Unknown ids — including anything from a previous window —
        # are refused below.
        if generation != self._generation:
            log.debug(
                "activation with old generation %d (current %d), id-checked",
                generation, self._generation,
            )
        item_id = self._item_id(node_id)
        if item_id is None or self._reg is None:
            log.warning("activation for unknown node %s", node_id)
            return False
        try:
            self._call_menu(
                "Event",
                GLib.Variant(
                    "(isvu)",
                    (item_id, "clicked", GLib.Variant("s", ""), int(time.time())),
                ),
            )
            log.info("clicked dbusmenu item %d", item_id)
            return True
        except Exception:
            log.exception("activation of %s failed", node_id)
            return False

    def opened(self, node_id: str) -> None:
        item_id = self._item_id(node_id)
        if item_id is None or self._reg is None:
            return
        try:
            self._call_menu(
                "Event",
                GLib.Variant(
                    "(isvu)",
                    (item_id, "opened", GLib.Variant("s", ""), int(time.time())),
                ),
            )
        except Exception:
            log.debug("opened event for %s failed", node_id, exc_info=True)

    def closed(self, node_id: str) -> None:
        item_id = self._item_id(node_id)
        if item_id is None or self._reg is None:
            return
        try:
            self._call_menu(
                "Event",
                GLib.Variant(
                    "(isvu)",
                    (item_id, "closed", GLib.Variant("s", ""), int(time.time())),
                ),
            )
        except Exception:
            log.debug("closed event for %s failed", node_id, exc_info=True)

    # -- dbusmenu client ------------------------------------------------------

    def _call_menu(self, method: str, params: GLib.Variant, reply_type: str | None = None):
        assert self._reg is not None
        return self._connection.call_sync(
            self._reg.sender,
            self._reg.path,
            DBUSMENU_IFACE,
            method,
            params,
            GLib.VariantType(reply_type) if reply_type else None,
            Gio.DBusCallFlags.NONE,
            CALL_TIMEOUT_MS,
            None,
        )

    def _about_to_show(self, item_id: int):
        try:
            self._call_menu("AboutToShow", GLib.Variant("(i)", (item_id,)), "(b)")
        except Exception:
            log.debug("AboutToShow(%d) failed", item_id, exc_info=True)

    def _fetch_children(self, reg: Registration, parent_id: int) -> Optional[list[MenuNode]]:
        """One GetLayout of depth 1 under parent_id, normalized. None on error."""
        try:
            result = self._connection.call_sync(
                reg.sender,
                reg.path,
                DBUSMENU_IFACE,
                "GetLayout",
                GLib.Variant("(iias)", (parent_id, 1, ITEM_PROPS)),
                GLib.VariantType("(u(ia{sv}av))"),
                Gio.DBusCallFlags.NONE,
                CALL_TIMEOUT_MS,
                None,
            )
        except Exception:
            log.warning(
                "GetLayout(%d) on %s%s failed", parent_id, reg.sender, reg.path,
                exc_info=True,
            )
            return None

        _revision, (_root_id, _root_props, children) = result.unpack()
        out: list[MenuNode] = []
        for child in children:
            node = self._normalize(child)
            if node is not None:
                out.append(node)
        return out

    def _normalize(self, item) -> Optional[MenuNode]:
        item_id, props, _grandchildren = item
        if props.get("visible", True) is False:
            return None
        self._known_ids.add(item_id)
        node_id = f"r{item_id}"

        if props.get("type") == "separator":
            return MenuNode(id=node_id, type=TYPE_SEPARATOR)

        toggle = props.get("toggle-type", "")
        if props.get("children-display") == "submenu":
            ntype = TYPE_SUBMENU
        elif toggle == "checkmark":
            ntype = TYPE_CHECKBOX
        elif toggle == "radio":
            ntype = TYPE_RADIO
        else:
            ntype = TYPE_ITEM

        return MenuNode(
            id=node_id,
            label=_strip_mnemonic(str(props.get("label", ""))),
            type=ntype,
            enabled=bool(props.get("enabled", True)),
            checked=int(props.get("toggle-state", 0)) == 1,
            accel=_shortcut_to_accel(props.get("shortcut")),
            children=None,
        )

    def _item_id(self, node_id: str) -> Optional[int]:
        if not node_id.startswith("r"):
            return None
        try:
            item_id = int(node_id[1:])
        except ValueError:
            return None
        return item_id if item_id in self._known_ids else None

    # -- live updates ---------------------------------------------------------

    def _subscribe(self, reg: Registration):
        self._unsubscribe()
        self._signal_sub = self._connection.signal_subscribe(
            reg.sender,
            DBUSMENU_IFACE,
            None,  # LayoutUpdated + ItemsPropertiesUpdated
            reg.path,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_menu_signal,
        )

    def _unsubscribe(self):
        if self._signal_sub:
            self._connection.signal_unsubscribe(self._signal_sub)
            self._signal_sub = 0

    def _on_menu_signal(self, _conn, _sender, _path, _iface, signal, params):
        # Children and item state are fetched fresh every time a menu opens,
        # so only a change to the top level (root LayoutUpdated) warrants a
        # re-claim. Reacting to child-level updates would churn generations —
        # Qt apps emit Layout/ItemsPropertiesUpdated storms in response to our
        # own AboutToShow.
        if signal != "LayoutUpdated":
            return
        _revision, parent = params.unpack()
        if parent == 0:
            log.debug("dbusmenu root layout changed")
            self._schedule_notify()

    def _reset(self):
        self._unsubscribe()
        self._reg = None
        self._known_ids = set()
