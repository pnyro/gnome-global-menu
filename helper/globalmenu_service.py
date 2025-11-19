#!/usr/bin/env python3
"""
Global Menu D-Bus Service
Exposes menu structures from focused windows via D-Bus for GNOME Shell extension.
"""

import sys
import signal
import json
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import pyatspi
from pyatspi import Registry, ROLE_MENU_BAR, ROLE_APPLICATION

from menu_serializer import MenuSerializer


# D-Bus interface details
BUS_NAME = "org.gnome.GlobalMenu"
OBJECT_PATH = "/org/gnome/GlobalMenu"
INTERFACE_NAME = "org.gnome.GlobalMenu"


class GlobalMenuService(dbus.service.Object):
    """D-Bus service that provides menu information for the focused window."""

    def __init__(self, bus):
        super().__init__(bus, OBJECT_PATH)
        self.bus = bus

        self.current_window = None
        self.current_menubar = None
        self.current_app = None
        self.current_app_with_menu = None  # Track which app owns the current menu
        self.serializer = MenuSerializer()

        # Current serialized menu (cached)
        self.current_menu_data = None

        # Statistics
        self.focus_changes = 0
        self.menus_extracted = 0

        print(f"✅ D-Bus service initialized on {BUS_NAME}")
        print(f"   Object path: {OBJECT_PATH}")
        print(f"   Interface: {INTERFACE_NAME}")

    def find_menubar(self, accessible, depth=0, max_depth=10):
        """Find MenuBar in accessible tree."""
        if depth > max_depth:
            return None

        try:
            if accessible.getRole() == ROLE_MENU_BAR:
                return accessible

            child_count = min(accessible.childCount, 100)
            for i in range(child_count):
                try:
                    child = accessible.getChildAtIndex(i)
                    if child:
                        result = self.find_menubar(child, depth + 1, max_depth)
                        if result:
                            return result
                except:
                    continue
        except:
            pass

        return None

    def on_window_activate(self, event):
        """Handle window activation events."""
        self.focus_changes += 1

        try:
            window = event.source

            # Skip if same window
            if window == self.current_window:
                return

            self.current_window = window

            # Get window info
            window_name = window.name or "(unnamed)"

            # Try to get the application
            app = None
            app_name = ""
            try:
                parent = window
                for _ in range(5):
                    if parent.getRole() == ROLE_APPLICATION:
                        app = parent
                        app_name = app.name or ""
                        break
                    try:
                        parent = parent.parent
                    except:
                        break
            except:
                pass

            # FIX: Ignore XWayland wrapper frames to prevent flickering
            if app_name == "mutter-x11-frames":
                return

            # FIX: Ignore focus changes to GNOME Shell (panel/overview)
            # This prevents the menu from disappearing when clicking the top bar
            if app_name == "gnome-shell":
                return

            self.current_app = app

            # Find menubar
            menubar = self.find_menubar(window)

            if menubar:
                self.current_menubar = menubar
                self.current_app_with_menu = app  # Remember this app has the menu
                self.menus_extracted += 1

                # Serialize menu structure
                self.current_menu_data = self.serializer.serialize_menu_tree(
                    menubar,
                    app_name=app_name,
                    window_title=window_name
                )

                menu_count = len(self.current_menu_data.get("menus", []))

                print(f"\n🪟 Menu extracted: {window_name} ({app_name})")
                print(f"   Menus: {menu_count} top-level")

                # Emit D-Bus signal
                self.MenuChanged(app_name, True)

            else:
                # LOGIC FIX: Child Window Persistence
                # If this window has no menu, but belongs to the same app 
                # that currently OWNS the menu, do not clear it.
                if app and self.current_app_with_menu and app == self.current_app_with_menu:
                    print(f"\n🪟 Dialog/Child detected: {window_name} (belonging to {app_name})")
                    print(f"   🛡️  Persisting existing menu")
                    return

                self.current_menubar = None
                self.current_menu_data = None
                self.current_app_with_menu = None # Reset tracker

                print(f"\n🪟 No menu: {window_name} ({app_name})")

                # Emit D-Bus signal
                self.MenuChanged(app_name, False)

        except Exception as e:
            print(f"⚠️  Error handling window activation: {e}")
            import traceback
            traceback.print_exc()

    @dbus.service.method(INTERFACE_NAME, out_signature='s')
    def GetCurrentMenu(self):
        """
        Get the current menu structure as JSON.

        Returns:
            JSON string with menu structure, or empty object if no menu
        """
        if self.current_menu_data:
            return json.dumps(self.current_menu_data)
        else:
            return json.dumps({
                "app_name": "",
                "window_title": "",
                "menus": []
            })

    @dbus.service.method(INTERFACE_NAME, in_signature='i', out_signature='b')
    def ActivateMenuItem(self, item_id):
        """
        Activate a menu item by its ID.

        Args:
            item_id: The unique ID of the menu item (from serialized data)

        Returns:
            True if activation succeeded, False otherwise
        """
        try:
            # Get the accessible object by ID
            menu_item = self.serializer.get_menu_item_by_id(item_id)

            if not menu_item:
                print(f"❌ Menu item ID {item_id} not found")
                return False

            # Get the action interface
            action_iface = menu_item.queryAction()

            if not action_iface or action_iface.nActions == 0:
                print(f"❌ Menu item '{menu_item.name}' has no actions")
                return False

            # Perform the action
            result = action_iface.doAction(0)

            if result:
                print(f"✅ Activated: {menu_item.name}")
                return True
            else:
                print(f"❌ Activation failed: {menu_item.name}")
                return False

        except Exception as e:
            print(f"❌ Error activating menu item: {e}")
            import traceback
            traceback.print_exc()
            return False

    @dbus.service.method(INTERFACE_NAME, in_signature='as', out_signature='b')
    def ActivateMenuItemByPath(self, path):
        """
        Activate a menu item by its path.

        Args:
            path: Array of menu labels, e.g., ["File", "New"]

        Returns:
            True if activation succeeded, False otherwise
        """
        if not self.current_menubar:
            print("❌ No menubar available")
            return False

        try:
            # Find the menu item by path
            menu_item = self.serializer.get_menu_item_by_path(self.current_menubar, path)

            if not menu_item:
                print(f"❌ Menu item not found: {' → '.join(path)}")
                return False

            # Get the action interface
            action_iface = menu_item.queryAction()

            if not action_iface or action_iface.nActions == 0:
                print(f"❌ Menu item '{menu_item.name}' has no actions")
                return False

            # Perform the action
            result = action_iface.doAction(0)

            if result:
                print(f"✅ Activated: {' → '.join(path)}")
                return True
            else:
                print(f"❌ Activation failed: {' → '.join(path)}")
                return False

        except Exception as e:
            print(f"❌ Error activating menu item: {e}")
            import traceback
            traceback.print_exc()
            return False

    @dbus.service.signal(INTERFACE_NAME, signature='sb')
    def MenuChanged(self, app_name, has_menu):
        """
        Signal emitted when the focused window changes.

        Args:
            app_name: Name of the application
            has_menu: True if the window has a menubar, False otherwise
        """
        pass  # Signal body is empty, handled by D-Bus

    @dbus.service.method(INTERFACE_NAME, out_signature='a{sv}')
    def GetStatistics(self):
        """Get service statistics."""
        return {
            "focus_changes": dbus.UInt32(self.focus_changes),
            "menus_extracted": dbus.UInt32(self.menus_extracted),
        }


def main():
    """Main entry point."""
    print("="*70)
    print("  GNOME Global Menu - D-Bus Service")
    print("="*70)

    # Initialize D-Bus main loop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Get session bus
    try:
        bus = dbus.SessionBus()
    except Exception as e:
        print(f"❌ Failed to connect to session bus: {e}")
        return 1

    # Request bus name
    try:
        name = dbus.service.BusName(BUS_NAME, bus)
    except dbus.exceptions.NameExistsException:
        print(f"❌ Service {BUS_NAME} is already running!")
        print("   Stop the existing instance first.")
        return 1

    # Create service instance
    service = GlobalMenuService(bus)

    # Register AT-SPI event listener
    print("\n🔍 Registering AT-SPI event listener...")
    try:
        Registry.registerEventListener(
            service.on_window_activate,
            "window:activate"
        )
        print("✅ Listening for window focus changes")
    except Exception as e:
        print(f"❌ Failed to register AT-SPI listener: {e}")
        return 1

    # Create GLib main loop
    loop = GLib.MainLoop()

    # Handle signals
    def signal_handler(sig, frame):
        print("\n\n⚠️  Stopping service...")
        print(f"   Focus changes: {service.focus_changes}")
        print(f"   Menus extracted: {service.menus_extracted}")
        loop.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("\n✅ Service running. Press Ctrl+C to stop.\n")
    print("="*70)

    # Run main loop
    try:
        loop.run()
    except KeyboardInterrupt:
        pass

    # Cleanup
    try:
        Registry.deregisterEventListener(
            service.on_window_activate,
            "window:activate"
        )
    except:
        pass

    print("\n👋 Service stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
