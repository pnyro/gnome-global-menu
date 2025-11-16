# Helper Scripts

This directory contains Python scripts for the GNOME Global Menu helper daemon.

## Validation Scripts

### `atspi_validate.py`
Validates that menu extraction from applications via AT-SPI works correctly.

**Usage:**
```bash
# Interactive mode (recommended)
python3 atspi_validate.py

# Workflow:
#   1. Lists all accessible apps
#   2. Press Enter (or 's') to scan which apps have MenuBars
#   3. Shows list of apps with menus
#   4. Enter a number to see detailed menu structure for that app
#   5. Returns to menu (can analyze another app or re-scan)
#   6. Press 'q' or Ctrl+C to exit

# Non-interactive: Scan all apps and exit
python3 atspi_validate.py ""

# Non-interactive: Analyze specific app and exit
python3 atspi_validate.py 16  # e.g., GIMP
```

**Features:**
- Lists all accessible applications
- Finds MenuBars in application windows
- Extracts and displays complete menu tree structure
- Shows menu items, submenus, separators, check items, radio items
- Identifies activatable menu items

### `test_activation.py`
Demonstrates menu item activation via AT-SPI `doAction()`.

**Usage:**
```bash
# Make sure GIMP is running first!
python3 test_activation.py
```

**What it does:**
- Finds GIMP's MenuBar
- Locates the "Help → About" menu item
- Asks for confirmation
- Activates the menu item (opens GIMP's About dialog)

## Requirements

**Python packages:**
- `pyatspi` (version 1.9.0 or later)
- `python-dbus` or `pydbus`

**System:**
- `at-spi2-core` (running)
- For Qt apps: `qt-at-spi` package

**Check dependencies:**
```bash
# Python packages
python3 -c "import pyatspi; print('pyatspi OK')"
python3 -c "import dbus; print('dbus OK')"

# AT-SPI daemon
ps aux | grep at-spi
```

## Test Applications

**Known to work (accessible menus):**
- ✅ GIMP (GTK2/3) - Full menu structure exposed
- ✅ LibreOffice - Complex menu structure
- ✅ Older GTK3 applications with traditional menu bars
- ✅ Qt apps (with QT_ACCESSIBILITY=1 environment variable)

**Known NOT to work:**
- ❌ Nautilus (Files) - GTK4 with hamburger menu
- ❌ ptyxis - GTK4 terminal
- ❌ Most modern GNOME apps (use client-side decorations)
- ❌ Chrome/Brave (without --force-renderer-accessibility flag)
- ❌ Flatpak apps (sandboxed AT-SPI bus)
- ❌ Electron apps (often no AT-SPI support)

## Why Some Apps Don't Appear

### Chromium Browsers (Chrome, Brave, Edge)
Chromium disables AT-SPI by default for performance. To enable:

```bash
# Temporary (one session)
google-chrome --force-renderer-accessibility
brave --force-renderer-accessibility

# Or enable in browser settings:
# Visit chrome://accessibility or brave://accessibility
# Enable "Accessibility" mode
```

### Flatpak Applications
Flatpak apps run in a sandbox with their own AT-SPI bus. Solutions:
- Install native packages instead of flatpak when possible
- Some flatpaks may not expose menus even with correct permissions

### GTK4 Applications
Modern GNOME apps often use client-side decorations without traditional menus:
- Files (Nautilus), Console, Text Editor use hamburger menus
- These won't work with global menu unless they expose DBusMenu

### Diagnostic Tool
Run the diagnostic tool to check your system:
```bash
python3 diagnose_atspi.py
```

## pyatspi API Notes

**Correct way to activate menu items:**
```python
# Get the action interface (not the deprecated get_action method)
action_iface = menu_item.queryAction()

# Check if actions are available
if action_iface and action_iface.nActions > 0:
    # Get action name
    action_name = action_iface.getName(0)

    # Perform the action
    result = action_iface.doAction(0)
```

**Avoid deprecated methods:**
- ❌ `accessible.get_action_name(0)` - deprecated
- ❌ `accessible.get_n_actions()` - deprecated
- ✅ `accessible.queryAction()` - use this instead

## Window Tracking Daemon

### `window_tracker.py`
Real-time window focus monitoring daemon that extracts menus as windows gain focus.

**Usage:**
```bash
# Run the daemon (press Ctrl+C to stop)
python3 window_tracker.py
```

**What it does:**
- Listens to AT-SPI `window:activate` events
- Automatically detects when window focus changes
- Extracts MenuBar structure from newly focused windows
- Displays menu information in real-time
- Shows statistics on exit

**Example output:**
```
======================================================================
🪟 Window activated: GNU Image Manipulation Program
   Role: frame
   Focus changes: 5
   App: gimp
   ✅ MenuBar found (11 menus)
   Menus: File, Edit, Select, View, Image, Layer, Colors, Tools, Filters, Windows, Help
   Total menus extracted: 3
======================================================================
```

**Use cases:**
- Test real-time menu extraction
- Monitor which apps expose accessible menus
- Debug focus tracking behavior
- Foundation for D-Bus service daemon

## Next Steps

1. ✅ AT-SPI validation complete
2. 🔄 Build window tracking (focus change events) - **IN PROGRESS**
3. ⏭️ Add D-Bus service layer
4. ⏭️ Create GNOME Shell extension
