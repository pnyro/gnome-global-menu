# Helper Scripts

This directory contains Python scripts for the GNOME Global Menu helper daemon.

## Validation Scripts

### `atspi_validate.py`
Validates that menu extraction from applications via AT-SPI works correctly.

**Usage:**
```bash
# Interactive mode - choose an app
python3 atspi_validate.py

# Scan all apps for menus
python3 atspi_validate.py ""

# Analyze a specific app by index
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
- GIMP (GTK2/3) - Full menu structure exposed
- Older GTK3 applications with traditional menu bars

**Known NOT to work:**
- Nautilus (Files) - GTK4 with hamburger menu
- ptyxis - GTK4 terminal
- Most modern GNOME apps (use client-side decorations)

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

## Next Steps

1. ✅ AT-SPI validation complete
2. ⏭️ Build window tracking (focus change events)
3. ⏭️ Add D-Bus service layer
4. ⏭️ Create GNOME Shell extension
