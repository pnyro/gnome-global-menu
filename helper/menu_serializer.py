#!/usr/bin/env python3
"""
Menu Serializer for GNOME Global Menu
Converts AT-SPI menu structures to JSON for D-Bus transmission.
"""

import json
from pyatspi import (
    ROLE_MENU_BAR,
    ROLE_MENU,
    ROLE_MENU_ITEM,
    ROLE_CHECK_MENU_ITEM,
    ROLE_RADIO_MENU_ITEM,
    ROLE_SEPARATOR,
)


class MenuSerializer:
    """Serializes AT-SPI menu trees to JSON."""

    def __init__(self):
        self.menu_item_map = {}  # Maps unique IDs to accessible objects for activation
        self.next_id = 0

    def serialize_menu_tree(self, menubar, app_name=None, window_title=None):
        """
        Serialize complete menu tree to JSON-compatible dict.

        Returns:
            dict with structure:
            {
                "app_name": str,
                "window_title": str,
                "menus": [...]  # Top-level menus
            }
        """
        self.menu_item_map = {}  # Reset map
        self.next_id = 0

        menus = []
        try:
            for i in range(menubar.childCount):
                child = menubar.getChildAtIndex(i)
                if child:
                    menu_data = self._serialize_accessible(child)
                    if menu_data:
                        menus.append(menu_data)
        except Exception as e:
            print(f"Error serializing menu tree: {e}")

        return {
            "app_name": app_name or "",
            "window_title": window_title or "",
            "menus": menus
        }

    def _serialize_accessible(self, accessible, depth=0, max_depth=20):
        """
        Recursively serialize an accessible object and its children.

        Returns dict with structure:
        {
            "id": int,           # Unique ID for activation
            "label": str,        # Display text
            "type": str,         # "menu", "menuitem", "separator", etc.
            "enabled": bool,     # Whether item is enabled
            "checked": bool,     # For check/radio items (optional)
            "children": [...]    # Submenu items (if type="menu")
        }
        """
        if depth > max_depth:
            return None

        try:
            role = accessible.getRole()
            name = accessible.name or ""

            # Determine item type
            item_type = self._get_item_type(role)
            if not item_type:
                return None

            # Create unique ID and store reference
            item_id = self.next_id
            self.next_id += 1
            self.menu_item_map[item_id] = accessible

            # Build item data
            item = {
                "id": item_id,
                "label": name,
                "type": item_type,
            }

            # Check if item is enabled
            try:
                state_set = accessible.getState()
                item["enabled"] = state_set.contains(pyatspi.STATE_ENABLED)

                # Check state for check/radio items
                if role in (ROLE_CHECK_MENU_ITEM, ROLE_RADIO_MENU_ITEM):
                    item["checked"] = state_set.contains(pyatspi.STATE_CHECKED)
            except:
                item["enabled"] = True

            # Check if item has an action (is activatable)
            try:
                action_iface = accessible.queryAction()
                item["activatable"] = (action_iface and action_iface.nActions > 0)
            except:
                item["activatable"] = False

            # Get accelerator/shortcut if available
            try:
                if hasattr(accessible, 'get_attributes'):
                    attrs = accessible.get_attributes()
                    if attrs:
                        for attr in attrs:
                            if 'shortcut' in attr.lower() or 'accel' in attr.lower():
                                # Parse accelerator (format varies)
                                item["accelerator"] = attr.split(':')[-1] if ':' in attr else attr
                                break
            except:
                pass

            # Recursively serialize children (submenus)
            if role in (ROLE_MENU_BAR, ROLE_MENU):
                children = []
                try:
                    for i in range(min(accessible.childCount, 100)):  # Limit to prevent hangs
                        child = accessible.getChildAtIndex(i)
                        if child:
                            child_data = self._serialize_accessible(child, depth + 1, max_depth)
                            if child_data:
                                children.append(child_data)
                except:
                    pass

                if children:
                    item["children"] = children

            return item

        except Exception as e:
            # Silently skip problematic items
            return None

    def _get_item_type(self, role):
        """Map AT-SPI role to menu item type string."""
        type_map = {
            ROLE_MENU_BAR: "menubar",
            ROLE_MENU: "menu",
            ROLE_MENU_ITEM: "menuitem",
            ROLE_CHECK_MENU_ITEM: "checkmenuitem",
            ROLE_RADIO_MENU_ITEM: "radiomenuitem",
            ROLE_SEPARATOR: "separator",
        }
        return type_map.get(role)

    def get_menu_item_by_id(self, item_id):
        """
        Get the AT-SPI accessible object for a menu item by its ID.
        Used for activation.
        """
        return self.menu_item_map.get(item_id)

    def get_menu_item_by_path(self, menubar, path):
        """
        Find a menu item by following a path of labels.

        Args:
            menubar: The MenuBar accessible object
            path: List of menu labels, e.g., ["File", "New", "Image..."]

        Returns:
            The accessible object, or None if not found
        """
        current = menubar

        for step in path:
            found = False
            try:
                for i in range(current.childCount):
                    child = current.getChildAtIndex(i)
                    if child and child.name == step:
                        current = child
                        found = True
                        break
            except:
                return None

            if not found:
                return None

        return current


# Import pyatspi for state constants
import pyatspi


if __name__ == "__main__":
    # Simple test
    print("MenuSerializer module loaded successfully")
    print("Use this from the D-Bus service or other scripts")
