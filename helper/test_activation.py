#!/usr/bin/env python3
"""
Menu Item Activation Test
Demonstrates how to activate a menu item via AT-SPI.
"""

import sys
import time
import pyatspi
from pyatspi import Registry, ROLE_MENU_BAR, ROLE_MENU, ROLE_MENU_ITEM


def find_menubar(accessible, depth=0, max_depth=10):
    """Recursively search for a MenuBar."""
    if depth > max_depth:
        return None

    try:
        if accessible.getRole() == ROLE_MENU_BAR:
            return accessible

        for i in range(accessible.childCount):
            child = accessible.getChildAtIndex(i)
            if child:
                result = find_menubar(child, depth + 1, max_depth)
                if result:
                    return result
    except:
        pass

    return None


def find_menu_item_by_path(menubar, *path):
    """
    Find a menu item by following a path of menu names.
    Example: find_menu_item_by_path(menubar, "Help", "About")
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
        except Exception as e:
            print(f"Error navigating to '{step}': {e}")
            return None

        if not found:
            print(f"Could not find menu item: {step}")
            return None

    return current


def activate_menu_item(menu_item):
    """Activate a menu item using doAction()."""
    try:
        # Get the action interface
        action_iface = menu_item.queryAction()

        if not action_iface:
            print(f"❌ Menu item '{menu_item.name}' has no action interface")
            return False

        n_actions = action_iface.nActions
        if n_actions == 0:
            print(f"❌ Menu item '{menu_item.name}' has no actions")
            return False

        # Get action details
        action_name = action_iface.getName(0)
        print(f"🎯 Activating: {menu_item.name} (action: {action_name})")

        # Perform the action
        result = action_iface.doAction(0)

        if result:
            print(f"✅ Successfully activated!")
            return True
        else:
            print(f"❌ Activation failed")
            return False

    except Exception as e:
        print(f"❌ Error during activation: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test script."""
    print("="*70)
    print("  AT-SPI Menu Item Activation Test")
    print("="*70)

    # Get GIMP app
    desktop = Registry.getDesktop(0)
    gimp = None

    print("\nSearching for GIMP...")
    for i in range(desktop.childCount):
        try:
            app = desktop.getChildAtIndex(i)
            if app and app.name == "gimp":
                gimp = app
                print(f"✅ Found GIMP (PID: {app.get_process_id()})")
                break
        except:
            pass

    if not gimp:
        print("❌ GIMP not found. Please start GIMP and try again.")
        return 1

    # Find MenuBar
    print("\nSearching for MenuBar...")
    menubar = find_menubar(gimp)

    if not menubar:
        print("❌ MenuBar not found")
        return 1

    print("✅ MenuBar found")

    # Test: Find and activate "Help → About"
    print("\n" + "="*70)
    print("Test: Activating 'Help → About' menu item")
    print("="*70)

    about_item = find_menu_item_by_path(menubar, "Help", "About")

    if not about_item:
        print("❌ Could not find 'Help → About' menu item")
        return 1

    print(f"\n✅ Found: Help → About")
    print(f"   Role: {about_item.getRoleName()}")
    print(f"   Name: {about_item.name}")

    # Ask for confirmation
    print("\n⚠️  This will open GIMP's About dialog.")
    try:
        response = input("Proceed with activation? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n\nCancelled")
        return 0

    if response != 'y':
        print("Cancelled")
        return 0

    # Activate
    print()
    success = activate_menu_item(about_item)

    print("\n" + "="*70)
    if success:
        print("✅ Test completed successfully!")
        print("\nIf the GIMP About dialog opened, menu activation is working.")
    else:
        print("❌ Test failed")
    print("="*70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
