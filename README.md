# GNOME Global Menu

macOS-style global menu bar for GNOME Shell - displays application menus in the top panel.

![Status: Prototype Complete](https://img.shields.io/badge/status-prototype%20complete-success)
![GNOME Shell: 45-47](https://img.shields.io/badge/GNOME%20Shell-45--48-blue)
![Python: 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)

## Overview

This project implements a **global menu bar** for GNOME (similar to macOS or Unity) using a two-component architecture:

1. **Helper daemon** (Python) - Extracts menu structures from applications via AT-SPI
2. **GNOME Shell extension** (GJS) - Displays menus in the top panel

The primary approach is **AT-SPI scraping** because it works on Wayland without compositor modifications and supports GTK3/Qt apps that expose accessible menu structures.

## Features

✅ **Real-time menu extraction** - Automatically detects focused window and extracts menus
✅ **Wayland support** - Works on Wayland (and X11)
✅ **Signal-based updates** - Instant menu changes when switching windows
✅ **Full menu activation** - Click menu items to trigger actions in applications
✅ **D-Bus architecture** - Clean separation between daemon and UI

## Architecture

```
┌─────────────────────────────────────┐
│    GNOME Shell Extension (GJS)      │
│  - Panel UI                         │
│  - D-Bus client                     │
│  - Menu builder                     │
└────────────┬────────────────────────┘
             │ D-Bus (org.gnome.GlobalMenu)
             ▼
┌─────────────────────────────────────┐
│    Helper Daemon (Python)           │
│  - AT-SPI event listener            │
│  - Menu extraction & serialization  │
│  - D-Bus service                    │
└────────────┬────────────────────────┘
             │ AT-SPI
             ▼
      ┌─────────────┐
      │ Applications│
      │ (GIMP, etc.)│
      └─────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
# Python packages
sudo dnf install python3-pyatspi python3-dbus python3-gobject

# Check installation
python3 -c "import pyatspi; print('pyatspi OK')"
python3 -c "import dbus; print('dbus OK')"
```

### 2. Start the Helper Daemon

```bash
cd helper
python3 globalmenu_service.py
```

Keep this running in a terminal.

### 3. Install the Extension

```bash
cd extension
./install.sh
```

### 4. Reload GNOME Shell

**On X11:**
- Press `Alt+F2`, type `r`, press Enter

**On Wayland:**
- Log out and log back in, OR:
  ```bash
  busctl --user call org.gnome.Shell /org/gnome/Shell org.gnome.Shell Eval s 'Meta.restart("Restarting…")'
  ```

### 5. Test with GIMP

1. Launch GIMP
2. Focus the GIMP window
3. Watch the menus appear in the top panel!

## Supported Applications

### ✅ Known to Work
- **GIMP** (GTK2/3) - Full menu structure
- **LibreOffice** - Complex menus
- **Older GTK3 apps** with traditional menu bars
- **Qt applications** (with `QT_ACCESSIBILITY=1`)

### ❌ Known Limitations
- **GTK4 apps** - No traditional menubar (Nautilus, GNOME Console, etc.)
- **Chromium browsers** - Need `--force-renderer-accessibility` flag
- **Flatpak apps** - Sandboxed AT-SPI bus (may not work)
- **Electron apps** - Often no AT-SPI support

## Project Structure

```
gnome-global-menu/
├── helper/                      # Python helper daemon
│   ├── globalmenu_service.py    # Main D-Bus service
│   ├── menu_serializer.py       # AT-SPI → JSON converter
│   ├── window_tracker.py        # Window focus monitoring
│   ├── atspi_validate.py        # Validation tool
│   ├── test_activation.py       # Activation testing
│   ├── diagnose_atspi.py        # Diagnostic tool
│   ├── test_dbus.sh             # D-Bus testing script
│   ├── README.md                # Helper documentation
│   └── TESTING.md               # Testing guide
│
├── extension/                   # GNOME Shell extension
│   ├── extension.js             # Main extension code
│   ├── prefs.js                 # Preferences UI
│   ├── metadata.json            # Extension metadata
│   ├── install.sh               # Installation script
│   └── README.md                # Extension documentation
│
├── example-gnome-extension/     # Reference extension
│   └── window-title-is-back/    # Example code
│
├── CLAUDE.md                    # Project instructions
├── CHATGPT.md                   # Design notes (from ChatGPT)
├── TESTING_PHASE4.md            # Complete testing guide
└── README.md                    # This file
```

## Development Phases

### ✅ Phase 1: AT-SPI Validation
- Menu extraction from applications
- Menu activation via `doAction()`
- Validation and testing tools

### ✅ Phase 2: Window Tracking
- Real-time focus change detection
- Automatic menu extraction on focus
- Statistics and monitoring

### ✅ Phase 3: D-Bus Service
- D-Bus interface design
- Menu serialization (AT-SPI → JSON)
- Service implementation and testing

### ✅ Phase 4: GNOME Shell Extension
- Panel UI implementation
- D-Bus client integration
- Menu rendering and activation
- **Status: PROTOTYPE COMPLETE**

## Testing

See **[TESTING_PHASE4.md](TESTING_PHASE4.md)** for comprehensive testing instructions.

### Quick Test

```bash
# Terminal 1: Start daemon
cd helper && python3 globalmenu_service.py

# Terminal 2: Install extension
cd extension && ./install.sh

# Terminal 3: Monitor logs
journalctl -f -o cat /usr/bin/gnome-shell | grep "Global Menu"

# Then: Launch GIMP and watch the magic! ✨
```

## D-Bus Interface

**Bus Name:** `org.gnome.GlobalMenu`
**Object Path:** `/org/gnome/GlobalMenu`

### Methods
```
GetCurrentMenu() → s (JSON string)
  Returns menu structure for focused window

ActivateMenuItem(i item_id) → b (boolean)
  Activates menu item by ID

ActivateMenuItemByPath(as path) → b (boolean)
  Activates menu item by path (e.g., ["File", "New"])

GetStatistics() → a{sv} (dict)
  Returns service statistics
```

### Signals
```
MenuChanged(s app_name, b has_menu)
  Emitted when focused window changes
```

## Debugging

### View Extension Logs
```bash
journalctl -f -o cat /usr/bin/gnome-shell | grep "Global Menu"
```

### Test D-Bus Service
```bash
cd helper
./test_dbus.sh
```

### Check Extension Status
```bash
gnome-extensions list --enabled | grep globalmenu
gnome-extensions info globalmenu@gnome-shell-extensions
```

### Manual D-Bus Testing
```bash
# Get current menu
gdbus call --session \
  --dest org.gnome.GlobalMenu \
  --object-path /org/gnome/GlobalMenu \
  --method org.gnome.GlobalMenu.GetCurrentMenu

# Monitor signals
gdbus monitor --session \
  --dest org.gnome.GlobalMenu \
  --object-path /org/gnome/GlobalMenu
```

## Future Improvements

### Performance
- [ ] Menu structure caching
- [ ] Debounce rapid focus changes
- [ ] Lazy-load deep submenu trees

### UI Enhancements
- [ ] App icon next to menus
- [ ] Keyboard navigation (Alt key)
- [ ] Mnemonic underlines (File)
- [ ] Better styling/theming

### Configuration
- [ ] Blacklist certain apps
- [ ] Panel position preference
- [ ] Per-app enable/disable
- [ ] Settings UI

### Polish
- [ ] Systemd service for daemon
- [ ] Auto-start on login
- [ ] Error recovery and robustness
- [ ] Packaging (RPM, DEB)

## Technical Details

### Why AT-SPI?
- ✅ Works on Wayland (no compositor patches needed)
- ✅ Supported by GTK3 and Qt applications
- ✅ Mature and stable API
- ❌ Depends on apps exposing accessible menus
- ❌ Doesn't work with GTK4 hamburger menus

### Alternative: DBusMenu/KDE Appmenu
See [CHATGPT.md](CHATGPT.md) for detailed discussion of the DBusMenu approach and why AT-SPI was chosen for this prototype.

## Contributing

This is a prototype implementation. Contributions welcome for:
- Performance optimizations
- UI improvements
- Support for more applications
- Bug fixes

## References

- **AT-SPI Documentation:** https://www.freedesktop.org/wiki/Accessibility/AT-SPI2/
- **GNOME Shell Extensions:** https://gjs.guide/extensions/
- **D-Bus Specification:** https://dbus.freedesktop.org/doc/dbus-specification.html
- **KDE Appmenu Protocol:** (See CHATGPT.md)

## License

[Specify your license here]

## Credits

Created as a proof-of-concept for global menu support in GNOME on Wayland.

Design based on discussions and research documented in CHATGPT.md.
Implementation guidance in CLAUDE.md for future development.
