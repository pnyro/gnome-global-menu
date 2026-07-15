"""Menu sources. Each source can claim a window and serve its menu."""

from __future__ import annotations

from typing import Optional

from ..model import MenuBar, MenuNode


class WindowInfo:
    """What the extension tells us about the focused window."""

    def __init__(self, pid: int = 0, app_id: str = "", title: str = "", xid: int = 0):
        self.pid = pid
        self.app_id = app_id
        self.title = title
        self.xid = xid

    @classmethod
    def from_dict(cls, d: dict) -> "WindowInfo":
        return cls(
            pid=int(d.get("pid", 0)),
            app_id=str(d.get("app_id", "")),
            title=str(d.get("title", "")),
            xid=int(d.get("xid", 0)),
        )

    def __repr__(self):
        return f"WindowInfo(pid={self.pid}, app_id={self.app_id!r}, title={self.title!r})"


class Source:
    """Base class for menu sources (tiers)."""

    name = "base"

    def claim(self, window: WindowInfo) -> Optional[MenuBar]:
        """Return a MenuBar (top level only) if this source can serve the
        window, else None. Called on focus change, must be fast."""
        raise NotImplementedError

    def get_children(self, node_id: str) -> Optional[list[MenuNode]]:
        """Fetch (fresh) children of a node. None if the node is unknown."""
        raise NotImplementedError

    def activate(self, generation: int, node_id: str) -> bool:
        raise NotImplementedError

    def opened(self, node_id: str) -> None:
        pass

    def closed(self, node_id: str) -> None:
        pass
