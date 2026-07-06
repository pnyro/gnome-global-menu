"""Tier 3: AT-SPI menu scraping.

Lazy by design: on focus we locate the app by PID and serialize only the
top-level menubar entries. Children are fetched (fresh) when the shell
actually opens a menu, so enabled/checked state is current the moment the
user sees it. Every extraction bumps a generation; activations carry the
generation so a stale UI can never trigger the wrong item.

Uses libatspi via GI directly (no pyatspi registry/event loop — focus comes
from the extension, we only make queries).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

from ..model import (  # noqa: E402
    TYPE_CHECKBOX,
    TYPE_ITEM,
    TYPE_RADIO,
    TYPE_SEPARATOR,
    TYPE_SUBMENU,
    MenuBar,
    MenuNode,
)
from . import Source, WindowInfo  # noqa: E402

log = logging.getLogger(__name__)

# Per-call timeout: a slow app must degrade, never hang the daemon.
ATSPI_CALL_TIMEOUT_MS = 300
# BFS budget when hunting for a menubar inside a window tree.
MAX_SEARCH_NODES = 2000
MAX_SEARCH_DEPTH = 12
MAX_CHILDREN = 200

_ROLE_TO_TYPE = {}  # populated lazily; Atspi.Role values


def _role_map():
    global _ROLE_TO_TYPE
    if not _ROLE_TO_TYPE:
        _ROLE_TO_TYPE = {
            Atspi.Role.MENU: TYPE_SUBMENU,
            Atspi.Role.MENU_ITEM: TYPE_ITEM,
            Atspi.Role.CHECK_MENU_ITEM: TYPE_CHECKBOX,
            Atspi.Role.RADIO_MENU_ITEM: TYPE_RADIO,
            Atspi.Role.SEPARATOR: TYPE_SEPARATOR,
        }
    return _ROLE_TO_TYPE


def _parse_keybinding(kb: str) -> Optional[str]:
    """ATK exposes keybindings as 'mnemonic;sequence;accelerator' (verified
    against LibreOffice: 'm;<Alt>vm;<Control>m'). Only the third field is a
    real accelerator; the first two are mnemonic navigation."""
    if not kb:
        return None
    parts = kb.split(";")
    if len(parts) >= 3 and parts[2]:
        return parts[2]
    return None


class AtspiSource(Source):
    name = "atspi"

    def __init__(self):
        Atspi.set_timeout(ATSPI_CALL_TIMEOUT_MS, -1)
        self._generation = 0
        self._nodes: dict[str, Atspi.Accessible] = {}
        self._next_node = 0
        self._pid = 0
        self._menubar: Optional[Atspi.Accessible] = None
        # diagnostics
        self.last_claim_ms = 0.0

    # -- claiming ---------------------------------------------------------

    def claim(self, window: WindowInfo) -> Optional[MenuBar]:
        t0 = time.monotonic()
        try:
            bar = self._claim(window)
        finally:
            self.last_claim_ms = (time.monotonic() - t0) * 1000
        return bar

    def _claim(self, window: WindowInfo) -> Optional[MenuBar]:
        if window.pid <= 0:
            return None

        # Same app refocused (window/tab/dialog switch): reuse the menubar if
        # it is still alive. This also gives dialog-of-same-app persistence.
        if window.pid == self._pid and self._alive(self._menubar):
            return self._serialize_bar(window)

        app = self._find_app_by_pid(window.pid)
        if app is None:
            self._reset()
            return None

        menubar = self._find_menubar(app, window.title)
        if menubar is None:
            self._reset()
            return None

        self._pid = window.pid
        self._menubar = menubar
        return self._serialize_bar(window)

    def _serialize_bar(self, window: WindowInfo) -> Optional[MenuBar]:
        self._generation += 1
        self._nodes.clear()
        self._next_node = 0

        menus: list[MenuNode] = []
        try:
            count = min(self._menubar.get_child_count(), MAX_CHILDREN)
            for i in range(count):
                child = self._menubar.get_child_at_index(i)
                if child is None:
                    continue
                node = self._serialize_node(child, shallow=True)
                if node is not None and node.label:
                    menus.append(node)
        except Exception:
            log.exception("serializing menubar top level failed")
            self._reset()
            return None

        if not menus:
            return None
        return MenuBar(
            source=self.name,
            generation=self._generation,
            app_id=window.app_id,
            menus=menus,
        )

    # -- lazy children ----------------------------------------------------

    def get_children(self, node_id: str) -> Optional[list[MenuNode]]:
        acc = self._nodes.get(node_id)
        if acc is None:
            return None
        out: list[MenuNode] = []
        try:
            # A GTK "menu" role wraps its items; some toolkits nest the list
            # one level down. Serialize direct children, unwrapping a single
            # intermediate MENU if that is all there is.
            children = self._direct_children(acc)
            if len(children) == 1 and self._safe_role(children[0]) == Atspi.Role.MENU:
                children = self._direct_children(children[0])
            for child in children:
                node = self._serialize_node(child, shallow=True)
                if node is not None:
                    out.append(node)
        except Exception:
            log.exception("get_children(%s) failed", node_id)
            return []
        return out

    def _direct_children(self, acc) -> list:
        result = []
        count = min(acc.get_child_count(), MAX_CHILDREN)
        for i in range(count):
            child = acc.get_child_at_index(i)
            if child is not None:
                result.append(child)
        return result

    # -- activation -------------------------------------------------------

    def activate(self, generation: int, node_id: str) -> bool:
        if generation != self._generation:
            log.warning(
                "stale activation: generation %d != current %d", generation, self._generation
            )
            return False
        acc = self._nodes.get(node_id)
        if acc is None:
            log.warning("activation for unknown node %s", node_id)
            return False
        try:
            action = acc.get_action_iface()
            if action is None or action.get_n_actions() < 1:
                log.warning("node %s (%r) has no actions", node_id, acc.get_name())
                return False
            ok = bool(action.do_action(0))
            log.info("activated %r -> %s", acc.get_name(), ok)
            return ok
        except Exception:
            log.exception("activation of %s failed", node_id)
            return False

    # -- serialization helpers ---------------------------------------------

    def _serialize_node(self, acc, shallow: bool) -> Optional[MenuNode]:
        role = self._safe_role(acc)
        ntype = _role_map().get(role)
        if ntype is None:
            return None

        node_id = f"n{self._next_node}"
        self._next_node += 1
        self._nodes[node_id] = acc

        if ntype == TYPE_SEPARATOR:
            return MenuNode(id=node_id, type=TYPE_SEPARATOR)

        name = ""
        enabled = True
        checked = False
        accel = None
        try:
            name = acc.get_name() or ""
            states = acc.get_state_set()
            enabled = states.contains(Atspi.StateType.ENABLED)
            if ntype in (TYPE_CHECKBOX, TYPE_RADIO):
                checked = states.contains(Atspi.StateType.CHECKED)
            action = acc.get_action_iface()
            if action is not None and action.get_n_actions() > 0:
                accel = _parse_keybinding(action.get_key_binding(0))
        except Exception:
            log.debug("partial serialization for node %s", node_id, exc_info=True)

        # A MENU role with no children behaves as a plain item (GTK exposes
        # some flat menubar entries as MENU).
        if ntype == TYPE_SUBMENU:
            try:
                if acc.get_child_count() == 0:
                    ntype = TYPE_ITEM
            except Exception:
                pass

        return MenuNode(
            id=node_id,
            label=name,
            type=ntype,
            enabled=enabled,
            checked=checked,
            accel=accel,
            children=None,
        )

    # -- app / menubar discovery -------------------------------------------

    def _find_app_by_pid(self, pid: int):
        try:
            desktop = Atspi.get_desktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app is None:
                    continue
                try:
                    if app.get_process_id() == pid:
                        return app
                except Exception:
                    continue
        except Exception:
            log.exception("desktop iteration failed")
        return None

    def _find_menubar(self, app, title: str):
        """BFS each window of the app for a MENU_BAR, preferring the window
        whose name matches the focused title. Budgeted: a pathological tree
        yields None rather than a stall."""
        windows = []
        try:
            for i in range(min(app.get_child_count(), 64)):
                w = app.get_child_at_index(i)
                if w is not None:
                    windows.append(w)
        except Exception:
            return None

        # Prefer exact title match, then the rest.
        windows.sort(key=lambda w: 0 if self._safe_name(w) == title else 1)

        budget = MAX_SEARCH_NODES
        for w in windows:
            found, budget = self._bfs_menubar(w, budget)
            if found is not None:
                return found
            if budget <= 0:
                break
        return None

    def _bfs_menubar(self, root, budget: int):
        queue = deque([(root, 0)])
        while queue and budget > 0:
            acc, depth = queue.popleft()
            budget -= 1
            role = self._safe_role(acc)
            if role == Atspi.Role.MENU_BAR:
                return acc, budget
            if depth >= MAX_SEARCH_DEPTH:
                continue
            # Menus never live inside documents/terminals; skip heavy leaves.
            if role in (
                Atspi.Role.DOCUMENT_TEXT,
                Atspi.Role.DOCUMENT_WEB,
                Atspi.Role.DOCUMENT_FRAME,
                Atspi.Role.TERMINAL,
                Atspi.Role.TABLE,
                Atspi.Role.TREE_TABLE,
                Atspi.Role.CANVAS,
            ):
                continue
            try:
                for i in range(min(acc.get_child_count(), MAX_CHILDREN)):
                    child = acc.get_child_at_index(i)
                    if child is not None:
                        queue.append((child, depth + 1))
            except Exception:
                continue
        return None, budget

    # -- misc ---------------------------------------------------------------

    def _alive(self, acc) -> bool:
        if acc is None:
            return False
        try:
            acc.get_child_count()
            return True
        except Exception:
            return False

    def _safe_role(self, acc):
        try:
            return acc.get_role()
        except Exception:
            return Atspi.Role.INVALID

    def _safe_name(self, acc) -> str:
        try:
            return acc.get_name() or ""
        except Exception:
            return ""

    def _reset(self):
        self._pid = 0
        self._menubar = None
