"""Normalized menu model shared by all sources.

This is the single schema the extension renders; sources translate into it.
See PLAN.md "Normalized menu schema".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


TYPE_ITEM = "item"
TYPE_SUBMENU = "submenu"
TYPE_SEPARATOR = "separator"
TYPE_CHECKBOX = "checkbox"
TYPE_RADIO = "radio"


@dataclass
class MenuNode:
    id: str
    label: str = ""
    type: str = TYPE_ITEM
    enabled: bool = True
    checked: bool = False
    accel: Optional[str] = None
    # None = not yet loaded (lazy); [] = known empty
    children: Optional[list["MenuNode"]] = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "enabled": self.enabled,
        }
        if self.type in (TYPE_CHECKBOX, TYPE_RADIO):
            d["checked"] = self.checked
        if self.accel:
            d["accel"] = self.accel
        if self.type == TYPE_SUBMENU:
            d["children"] = (
                [c.to_dict() for c in self.children]
                if self.children is not None
                else None
            )
        return d


@dataclass
class MenuBar:
    source: str
    generation: int
    app_id: str = ""
    menus: list[MenuNode] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "source": self.source,
                "generation": self.generation,
                "app_id": self.app_id,
                "menus": [m.to_dict() for m in self.menus],
            }
        )


EMPTY_BAR_JSON = json.dumps(
    {"source": "", "generation": 0, "app_id": "", "menus": []}
)


def children_to_json(generation: int, nodes: list[MenuNode]) -> str:
    return json.dumps(
        {
            "generation": generation,
            "children": [n.to_dict() for n in nodes],
        }
    )
