# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project implements a **global menu bar for GNOME** (macOS-style menu in the top panel) using a two-component architecture:

1. **Helper daemon** (Python/Rust) - Extracts menu structures from applications via AT-SPI (accessibility) or DBusMenu
2. **GNOME Shell extension** (GJS/JavaScript) - Displays menus in the top panel and handles user interaction

The primary approach is **AT-SPI scraping** because it works on Wayland without compositor modifications and supports GTK3/Qt apps that expose accessible menu structures.

## Architecture

### Two-Component Design

**Helper Daemon (Python recommended for prototyping):**
- Subscribes to AT-SPI events to track the active window
- Extracts MenuBar tree using AT-SPI roles: `MenuBar`, `Menu`, `MenuItem`
- Serializes menu structure to JSON
- Exposes API over session D-Bus or UNIX socket
- Handles menu item activation via AT-SPI `doAction()` calls

**GNOME Shell Extension (GJS):**
- Adds a panel item to the top bar
- Queries helper daemon when active window changes
- Builds panel menu UI from JSON menu structure
- Sends activation requests to helper when user clicks menu items
- Implements keyboard navigation (Alt key, mnemonics)

### Key Dependencies

**Python helper:**
- `pyatspi` - AT-SPI interface for menu extraction
- `python-dbus` or `pydbus` - D-Bus IPC
- `gobject-introspection` - GObject bindings
- System: `at-spi2-core` (standard on GNOME), `qt-at-spi` for Qt apps

**GNOME Shell extension:**
- GJS (GNOME JavaScript)
- `imports.ui.panelMenu` - Panel UI components
- `imports.ui.main` - Shell integration

## Implementation Approaches

### Primary: AT-SPI Approach (Recommended)
- Works on Wayland without compositor patches
- Supports GTK3/Qt apps with accessible menus
- Does NOT work with GTK4 apps that lack menu bars by design
- Testing tool: `atspi-tools` to inspect accessible objects

### Alternative: DBusMenu/kde-appmenu (Hard)
- Requires either:
  - (A) Patching Mutter to implement KDE appmenu Wayland protocol, or
  - (B) Userspace proxy with app exporters (fragile on Wayland)
- Only pursue if AT-SPI approach fails for critical apps

## Development Workflow

### Phase 1: Python Helper Prototype
1. Write script using `pyatspi` to print menu trees for active window
2. Test menu extraction with target apps (GIMP, LibreOffice, Qt apps)
3. Implement `doAction()` activation for menu items
4. Expose D-Bus API for menu queries and activation

### Phase 2: GNOME Shell Extension
1. Create extension skeleton with metadata.json
2. Add panel button that queries helper via D-Bus
3. Build menu UI from JSON response
4. Wire click events to helper activation calls

### Phase 3: Hardening
1. Implement keyboard navigation (Alt to focus, mnemonics)
2. Add caching and performance optimizations
3. Handle focus/blur edge cases
4. Add toggle/blacklist for misbehaving apps
5. Handle dynamic menu changes (AT-SPI objects move/disappear)

## Critical Implementation Notes

### AT-SPI Menu Extraction
- Use AT-SPI roles: `MenuBar` (top-level), `Menu` (submenus), `MenuItem` (items)
- Menu activation: call `doAction(0)` on the accessible object
- Read `accelerator` property for keyboard shortcuts
- Listen to AT-SPI events for dynamic menu updates

### Wayland Considerations
- AT-SPI works on Wayland (unlike some X11-only approaches)
- Compositor features like xdg-dbus-annotation are NOT required for AT-SPI approach
- DBusMenu exporters on Wayland require compositor protocol support (why AT-SPI is preferred)

### Known Limitations
- GTK4 apps often have no traditional menu bar (client-side decorations with hamburger menus)
- Some apps may not expose menus via AT-SPI correctly
- Accelerator/mnemonic mapping requires extra handling
- Latency when switching windows needs optimization

## File Structure (To Be Created)

```
helper/                  # Python daemon
  menu_extractor.py      # AT-SPI menu extraction logic
  dbus_service.py        # D-Bus API exposure
  main.py               # Entry point

extension/              # GNOME Shell extension
  extension.js          # Main extension code
  metadata.json         # Extension metadata
  prefs.js             # Preferences UI (optional)
  stylesheet.css       # Custom styles (optional)

tests/                  # Test scripts
  test_apps/           # Sample apps for testing

docs/                   # Additional documentation
```

## Testing Strategy

### Manual Testing Apps
- **GTK3:** GIMP, older GTK apps with menu bars
- **Qt:** Qt-based applications with traditional menus
- **LibreOffice:** Complex menu structure
- **Verify:** Use `atspi-tools` to inspect menu accessibility

### Testing Commands
```bash
# Inspect AT-SPI tree for running app
accerciser  # GUI tool for AT-SPI inspection

# Test Python AT-SPI access
python3 -c "import pyatspi; print(pyatspi.Registry.getDesktop(0))"

# Check if at-spi2-core is running
ps aux | grep at-spi

# Install GNOME Shell extension (during development)
ln -s /path/to/extension ~/.local/share/gnome-shell/extensions/your-extension@uuid
gnome-extensions enable your-extension@uuid
# Reload GNOME Shell: Alt+F2, type 'r', Enter (X11 only)
# On Wayland: log out and back in, or use `busctl --user call org.gnome.Shell...`
```

## Technical References

See CHATGPT.md for detailed explanations of:
- KDE appmenu Wayland protocol
- DBusMenu specification
- Historical context of global menus on Linux
- Wayland vs X11 differences
- AT-SPI / GTK accessibility architecture
