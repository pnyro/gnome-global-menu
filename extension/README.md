# Global Menu GNOME Shell Extension

macOS-style global menu bar that displays application menus in the top panel.

## Prerequisites

1. **Helper daemon must be running**
   ```bash
   cd /home/diablo/Projects/gnome-global-menu/helper
   python3 globalmenu_service.py
   ```

2. **Application with accessible menus** (e.g., GIMP, LibreOffice)

## Installation

### Development Installation (Recommended for Testing)

```bash
# Create symlink to local extensions directory
mkdir -p ~/.local/share/gnome-shell/extensions
ln -s /home/diablo/Projects/gnome-global-menu/extension \
      ~/.local/share/gnome-shell/extensions/globalmenu@gnome-shell-extensions

# Reload GNOME Shell
# On X11: Alt+F2, type 'r', press Enter
# On Wayland: Log out and log back in, OR:
busctl --user call org.gnome.Shell /org/gnome/Shell org.gnome.Shell Eval s 'Meta.restart("Restarting…")'

# Enable the extension
gnome-extensions enable globalmenu@gnome-shell-extensions

# Check if enabled
gnome-extensions list --enabled | grep globalmenu
```

### Verify Installation

```bash
# Check extension info
gnome-extensions info globalmenu@gnome-shell-extensions

# View logs
journalctl -f -o cat /usr/bin/gnome-shell
# Or simpler:
journalctl -f | grep -i "global menu"
```

## Usage

1. **Start the helper daemon**
   ```bash
   cd /home/diablo/Projects/gnome-global-menu/helper
   python3 globalmenu_service.py
   ```

2. **Open GIMP** (or any app with accessible menus)

3. **Switch focus to GIMP** - The menu should appear in the top panel!

4. **Click on menu items** - They should activate in the application

## Testing

### Check Extension is Loaded
```bash
gnome-extensions list --enabled | grep globalmenu
```

### View Extension Logs
```bash
# Real-time logs
journalctl -f -o cat /usr/bin/gnome-shell

# Recent logs
journalctl -b -o cat /usr/bin/gnome-shell | grep "Global Menu"
```

### Debug Steps

**Problem: Extension not loading**
```bash
# Check for errors
gnome-extensions show globalmenu@gnome-shell-extensions

# Check logs for errors
journalctl -b -o cat /usr/bin/gnome-shell | grep -i error
```

**Problem: No menu appears**
1. Check helper daemon is running: `ps aux | grep globalmenu_service`
2. Check D-Bus service is available: `gdbus introspect --session --dest org.gnome.GlobalMenu --object-path /org/gnome/GlobalMenu`
3. Check extension logs: `journalctl -f -o cat /usr/bin/gnome-shell`
4. Make sure GIMP has focus (not the terminal)

**Problem: Menu items don't activate**
- Check helper daemon logs for activation errors
- Verify menu structure with: `gdbus call --session --dest org.gnome.GlobalMenu --object-path /org/gnome/GlobalMenu --method org.gnome.GlobalMenu.GetCurrentMenu`

## Uninstallation

```bash
# Disable extension
gnome-extensions disable globalmenu@gnome-shell-extensions

# Remove symlink
rm ~/.local/share/gnome-shell/extensions/globalmenu@gnome-shell-extensions

# Reload GNOME Shell (X11)
# Alt+F2, type 'r', press Enter
```

## Development

### Live Reload During Development

On X11:
```bash
# After making changes to extension.js:
# 1. Reload GNOME Shell: Alt+F2, type 'r', press Enter
# Extension changes will be picked up automatically
```

On Wayland:
```bash
# After making changes:
# 1. Disable extension
gnome-extensions disable globalmenu@gnome-shell-extensions

# 2. Restart GNOME Shell
busctl --user call org.gnome.Shell /org/gnome/Shell org.gnome.Shell Eval s 'Meta.restart("Restarting…")'

# 3. Re-enable extension
gnome-extensions enable globalmenu@gnome-shell-extensions
```

### View Console Logs
```bash
# See log() and logError() output
journalctl -f -o cat /usr/bin/gnome-shell | grep "Global Menu"
```

## Architecture

```
┌─────────────────────────────────────────┐
│       GNOME Shell Extension (GJS)       │
│  ┌───────────────────────────────────┐  │
│  │  GlobalMenuIndicator              │  │
│  │  - Panel button                   │  │
│  │  - D-Bus proxy                    │  │
│  │  - Menu builder                   │  │
│  └───────────────────────────────────┘  │
└─────────────────┬───────────────────────┘
                  │ D-Bus
                  │ org.gnome.GlobalMenu
                  ▼
┌─────────────────────────────────────────┐
│    Helper Daemon (Python)               │
│  ┌───────────────────────────────────┐  │
│  │  globalmenu_service.py            │  │
│  │  - AT-SPI event listener          │  │
│  │  - Menu extraction                │  │
│  │  - D-Bus service                  │  │
│  └───────────────────────────────────┘  │
└─────────────────┬───────────────────────┘
                  │ AT-SPI
                  ▼
         ┌─────────────────┐
         │  Applications   │
         │  (GIMP, etc.)   │
         └─────────────────┘
```

## Files

- **metadata.json** - Extension metadata (name, version, supported shell versions)
- **extension.js** - Main extension code (D-Bus client, UI builder)
- **prefs.js** - Preferences UI (future: blacklist, settings)

## Known Limitations

- Only works with applications that expose accessible menus via AT-SPI
- GTK4 apps with hamburger menus won't work (no traditional menubar)
- Chromium browsers need `--force-renderer-accessibility` flag
- Flatpak apps may not work due to sandboxing
