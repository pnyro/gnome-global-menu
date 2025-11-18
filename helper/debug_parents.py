#!/usr/bin/env python3
import pyatspi
from pyatspi import Registry, ROLE_MENU_BAR, ROLE_APPLICATION

def on_window_activate(event):
    window = event.source
    print(f"\n⬇️  FOCUS: {window.name} (Role: {window.getRoleName()})")
    
    # Check for menu
    has_menu = False
    try:
        for i in range(window.childCount):
            if window.getChildAtIndex(i).getRole() == ROLE_MENU_BAR:
                has_menu = True
                break
    except: pass
    
    print(f"    Has Menu: {has_menu}")

    # TRAVERSE UP THE TREE
    print("    Hierarchy:")
    try:
        parent = window.parent
        depth = 0
        while parent and depth < 5:
            print(f"      ⬆️  Parent {depth+1}: {parent.name} (Role: {parent.getRoleName()})")
            if parent.getRole() == ROLE_APPLICATION:
                print(f"         🎯 Found App: {parent.name}")
            parent = parent.parent
            depth += 1
    except Exception as e:
        print(f"      ⚠️ Error traversing parents: {e}")

Registry.registerEventListener(on_window_activate, "window:activate")
print("🕵️  Debugging Parent Hierarchy. Open GIMP -> Click 'About'...")
Registry.start()
