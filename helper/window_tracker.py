#!/usr/bin/env python3
"""
Window Tracking Daemon for GNOME Global Menu
Monitors window focus changes and extracts menu structures via AT-SPI.
"""

import sys
import signal
import pyatspi
from pyatspi import (
    Registry,
    ROLE_MENU_BAR,
    ROLE_MENU,
    ROLE_MENU_ITEM,
    ROLE_APPLICATION,
    ROLE_FRAME,
)


class WindowTracker:
    """Tracks focused window and extracts menu structures."""

    def __init__(self):
        self.current_window = None
        self.current_menubar = None
        self.menu_cache = {}  # Cache menus by window ID to avoid re-extraction

        # Statistics
        self.focus_changes = 0
        self.menus_extracted = 0

    def find_menubar(self, accessible, depth=0, max_depth=10):
        """
        Recursively search for a MenuBar in the accessible tree.
        Returns the first MenuBar found, or None.
        """
        if depth > max_depth:
            return None

        try:
            # Check if this object is a MenuBar
            if accessible.getRole() == ROLE_MENU_BAR:
                return accessible

            # Recursively check children (with limit to prevent hangs)
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

    def extract_menu_structure(self, menubar):
        """
        Extract menu structure from a MenuBar.
        Returns a list of top-level menu names.
        """
        menus = []
        try:
            for i in range(menubar.childCount):
                child = menubar.getChildAtIndex(i)
                if child and child.name:
                    menus.append(child.name)
        except Exception as e:
            print(f"  ⚠️  Error extracting menus: {e}")

        return menus

    def on_window_activate(self, event):
        """
        Called when a window is activated (receives focus).
        Extract menu structure if available.
        """
        self.focus_changes += 1

        try:
            # Get the source object (the activated window/frame)
            window = event.source

            # Skip if same window
            if window == self.current_window:
                return

            self.current_window = window

            # Get window info
            window_name = window.name or "(unnamed)"
            window_role = window.getRoleName()

            print(f"\n{'='*70}")
            print(f"🪟 Window activated: {window_name}")
            print(f"   Role: {window_role}")
            print(f"   Focus changes: {self.focus_changes}")

            # Try to get the application
            app = None
            try:
                # Navigate up to find the application
                parent = window
                for _ in range(5):  # Limit depth
                    if parent.getRole() == ROLE_APPLICATION:
                        app = parent
                        break
                    try:
                        parent = parent.parent
                    except:
                        break

                if app:
                    print(f"   App: {app.name}")
            except Exception as e:
                print(f"   App: (could not determine)")

            # Find menubar
            menubar = self.find_menubar(window)

            if menubar:
                self.current_menubar = menubar
                self.menus_extracted += 1

                menus = self.extract_menu_structure(menubar)

                print(f"   ✅ MenuBar found ({len(menus)} menus)")
                print(f"   Menus: {', '.join(menus)}")
                print(f"   Total menus extracted: {self.menus_extracted}")
            else:
                self.current_menubar = None
                print(f"   ❌ No MenuBar found")

        except Exception as e:
            print(f"⚠️  Error handling window activation: {e}")
            import traceback
            traceback.print_exc()

    def start(self):
        """Start listening to window activation events."""
        print("="*70)
        print("  GNOME Global Menu - Window Tracker")
        print("="*70)
        print("\nStarting window focus monitoring...")
        print("Press Ctrl+C to stop\n")

        try:
            # Register event listener for window activation
            Registry.registerEventListener(
                self.on_window_activate,
                "window:activate"
            )

            print("✅ Listening for window focus changes...")
            print(f"   Watching for: window:activate events")
            print(f"   AT-SPI Registry: {Registry}\n")

            # Start the main loop
            Registry.start()

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            self.stop()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            self.stop()

    def stop(self):
        """Stop listening and clean up."""
        print("\n" + "="*70)
        print("  Statistics")
        print("="*70)
        print(f"  Focus changes detected: {self.focus_changes}")
        print(f"  Menus extracted: {self.menus_extracted}")
        print("="*70)
        print("👋 Window tracker stopped")

        try:
            Registry.deregisterEventListener(
                self.on_window_activate,
                "window:activate"
            )
        except:
            pass


def main():
    """Main entry point."""
    tracker = WindowTracker()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\n⚠️  Received signal, stopping...")
        tracker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start tracking
    tracker.start()

    return 0


if __name__ == "__main__":
    sys.exit(main())
