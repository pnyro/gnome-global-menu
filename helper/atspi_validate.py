#!/usr/bin/env python3
"""
AT-SPI Validation Script for GNOME Global Menu
This script validates that we can extract menu structures from running applications.
"""

import sys
import pyatspi
from pyatspi import (
    Registry,
    ROLE_MENU_BAR,
    ROLE_MENU,
    ROLE_MENU_ITEM,
    ROLE_APPLICATION,
    ROLE_FRAME,
)


def print_header(text):
    """Print a formatted header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")


def get_accessible_apps():
    """Get all accessible applications."""
    print_header("Scanning Accessible Applications")

    desktop = Registry.getDesktop(0)
    apps = []

    for i in range(desktop.childCount):
        try:
            app = desktop.getChildAtIndex(i)
            if app and app.name:
                apps.append(app)
                print(f"  [{i}] {app.name} (PID: {app.get_process_id() if hasattr(app, 'get_process_id') else 'N/A'})")
        except Exception as e:
            print(f"  [!] Error accessing app at index {i}: {e}")

    return apps


def find_menubar(accessible, depth=0, max_depth=10):
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
        child_count = min(accessible.childCount, 100)  # Limit children to prevent hangs
        for i in range(child_count):
            try:
                child = accessible.getChildAtIndex(i)
                if child:
                    result = find_menubar(child, depth + 1, max_depth)
                    if result:
                        return result
            except:
                # Skip problematic children
                continue
    except Exception as e:
        # Silently ignore errors (some objects may not be accessible)
        pass

    return None


def print_menu_tree(accessible, indent=0, show_actions=False):
    """
    Recursively print the menu structure.
    Returns a list of (path, accessible) tuples for menu items.
    """
    menu_items = []

    try:
        role = accessible.getRole()
        name = accessible.name or "(unnamed)"

        # Get role name
        role_name = accessible.getRoleName()

        # Build indent
        prefix = "  " * indent

        # Get additional info
        info_parts = [f"{role_name}"]

        # Check for accelerator/keyboard shortcut
        if hasattr(accessible, 'get_attributes'):
            try:
                attrs = accessible.get_attributes()
                if attrs:
                    # Look for keyboard shortcut
                    for attr in attrs:
                        if 'shortcut' in attr.lower() or 'accel' in attr.lower():
                            info_parts.append(attr)
            except:
                pass

        # Check for actions
        action_count = 0
        try:
            action_iface = accessible.queryAction()
            if action_iface:
                action_count = action_iface.nActions
                if show_actions and action_count > 0:
                    action_name = action_iface.getName(0)
                    info_parts.append(f"action: {action_name}")
        except:
            pass

        info = " | ".join(info_parts)

        # Print this node
        symbol = "├─" if indent > 0 else "▸"
        print(f"{prefix}{symbol} {name} ({info})")

        # Store menu items for later activation testing
        if role == ROLE_MENU_ITEM and action_count > 0:
            path = f"{prefix}{name}"
            menu_items.append((path, accessible))

        # Recursively print children
        for i in range(accessible.childCount):
            child = accessible.getChildAtIndex(i)
            if child:
                child_items = print_menu_tree(child, indent + 1, show_actions)
                menu_items.extend(child_items)

    except Exception as e:
        print(f"{prefix}[!] Error: {e}")

    return menu_items


def test_app_menus(app):
    """Test menu extraction for a specific application."""
    print_header(f"Analyzing: {app.name}")

    # Find MenuBar
    print("\n🔍 Searching for MenuBar...")
    menubar = find_menubar(app)

    if not menubar:
        print("  ❌ No MenuBar found in this application")
        return None

    print(f"  ✅ MenuBar found! ({menubar.childCount} top-level menus)")

    # Print menu structure
    print("\n📋 Menu Structure:")
    menu_items = print_menu_tree(menubar, show_actions=True)

    return menu_items


def demonstrate_activation(menu_items):
    """Demonstrate menu item activation."""
    if not menu_items:
        print("\n  ℹ️  No activatable menu items found")
        return

    print_header("Menu Item Activation Test")
    print(f"\nFound {len(menu_items)} activatable menu items.")
    print("The first few items:")

    for i, (path, accessible) in enumerate(menu_items[:5]):
        try:
            action_iface = accessible.queryAction()
            action_name = action_iface.getName(0) if action_iface and action_iface.nActions > 0 else "N/A"
            print(f"  [{i}] {path.strip()} → Action: {action_name}")
        except Exception as e:
            print(f"  [{i}] {path.strip()} → Error: {e}")

    print("\n⚠️  Note: To actually activate a menu item, use:")
    print("     action_iface = menu_items[0][1].queryAction()")
    print("     action_iface.doAction(0)")
    print("     (Not executing to avoid unintended actions on your system)")


def scan_all_apps(apps):
    """Scan all apps for MenuBars and return list of apps with menus."""
    print("\n🔄 Scanning all applications for menus...")
    print("   (This may take a moment for apps with complex UI)\n")
    apps_with_menus = []

    for idx, app in enumerate(apps):
        # Show progress with actual index [idx] and progress (current/total)
        print(f"  [{idx}] Checking {app.name} ({idx+1}/{len(apps)})...", end='', flush=True)
        try:
            menubar = find_menubar(app)
            if menubar:
                print(f" ✅ MenuBar found ({menubar.childCount} menus)")
                apps_with_menus.append((idx, app, menubar.childCount))
            else:
                print(f" ❌ No MenuBar")
        except Exception as e:
            print(f" ⚠️  Error: {e}")

    return apps_with_menus


def main():
    """Main validation script."""
    import sys

    print_header("AT-SPI Validation for GNOME Global Menu")
    print("This script validates menu extraction from accessible applications.\n")

    # Get all applications
    apps = get_accessible_apps()

    if not apps:
        print("\n❌ No accessible applications found!")
        print("   Make sure you have applications running with menu bars.")
        return 1

    print(f"\n✅ Found {len(apps)} accessible applications")

    # Check for command-line argument (non-interactive mode)
    if len(sys.argv) > 1:
        choice = sys.argv[1]

        if choice == "":
            # Scan all apps
            apps_with_menus = scan_all_apps(apps)

            if apps_with_menus:
                print(f"\n✅ {len(apps_with_menus)} application(s) with accessible menus found!")
            else:
                print("\n❌ No applications with accessible MenuBars found.")
                print("   Try running apps like: GIMP or LibreOffice")
        else:
            # Analyze specific app
            try:
                idx = int(choice)
                if 0 <= idx < len(apps):
                    menu_items = test_app_menus(apps[idx])
                    if menu_items:
                        demonstrate_activation(menu_items)
                else:
                    print(f"❌ Invalid choice: {idx}")
                    return 1
            except ValueError:
                print("❌ Invalid input - must be a number")
                return 1

        print("\n" + "="*70)
        print("✅ Validation complete!")
        print("="*70)
        return 0

    # Interactive mode - loop until user exits
    apps_with_menus = None

    while True:
        try:
            print("\n" + "="*70)
            print("Choose an option:")
            print("  • Enter a number (0-{}) to analyze that app's menus".format(len(apps)-1))
            if apps_with_menus:
                print("  • Press 's' to re-scan all apps")
            else:
                print("  • Press 's' (or Enter) to scan all apps for MenuBars")
            print("  • Press 'q' or Ctrl+C to quit")
            print("="*70)

            choice = input("\nYour choice: ").strip().lower()

            if choice == 'q':
                print("\n👋 Goodbye!")
                return 0
            elif choice == 's' or (choice == '' and not apps_with_menus):
                # Scan all apps
                apps_with_menus = scan_all_apps(apps)

                if apps_with_menus:
                    print(f"\n✅ {len(apps_with_menus)} application(s) with accessible menus:")
                    for idx, app, menu_count in apps_with_menus:
                        print(f"     [{idx}] {app.name} ({menu_count} menus)")
                    print("\nEnter an app number to see detailed menu structure.")
                else:
                    print("\n❌ No applications with accessible MenuBars found.")
                    print("   Try running apps like: GIMP or LibreOffice")
            elif choice == '':
                if apps_with_menus:
                    print("⚠️  Already scanned. Enter an app number or 's' to re-scan.")
                else:
                    # First time, scan automatically
                    apps_with_menus = scan_all_apps(apps)
                    if apps_with_menus:
                        print(f"\n✅ {len(apps_with_menus)} application(s) with accessible menus:")
                        for idx, app, menu_count in apps_with_menus:
                            print(f"     [{idx}] {app.name} ({menu_count} menus)")
            else:
                # Try to parse as app number
                try:
                    idx = int(choice)
                    if 0 <= idx < len(apps):
                        menu_items = test_app_menus(apps[idx])
                        if menu_items:
                            demonstrate_activation(menu_items)
                    else:
                        print(f"❌ Invalid choice: {idx} (must be 0-{len(apps)-1})")
                except ValueError:
                    print("❌ Invalid input - enter a number, 's', or 'q'")

        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Goodbye!")
            return 0
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    sys.exit(main())
