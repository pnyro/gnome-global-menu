#!/bin/bash
# Installation script for Global Menu extension

set -e

EXTENSION_UUID="globalmenu@gnome-shell-extensions"
EXTENSION_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_DIR="$HOME/.local/share/gnome-shell/extensions/$EXTENSION_UUID"

echo "========================================================================"
echo "  Installing Global Menu Extension"
echo "========================================================================"
echo ""

# Create extensions directory if needed
mkdir -p "$HOME/.local/share/gnome-shell/extensions"

# Remove existing installation/symlink
if [ -e "$INSTALL_DIR" ]; then
    echo "Removing existing installation..."
    rm -rf "$INSTALL_DIR"
fi

# Create symlink
echo "Creating symlink..."
ln -s "$EXTENSION_DIR" "$INSTALL_DIR"
echo "✅ Symlink created: $INSTALL_DIR -> $EXTENSION_DIR"
echo ""

# Enable extension
echo "Enabling extension..."
gnome-extensions enable $EXTENSION_UUID 2>/dev/null || true
echo ""

# Check status
echo "Extension status:"
gnome-extensions info $EXTENSION_UUID 2>/dev/null || echo "⚠️  Extension not loaded yet"
echo ""

echo "========================================================================"
echo "  Installation Complete!"
echo "========================================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the helper daemon:"
echo "   cd ../helper && python3 globalmenu_service.py"
echo ""
echo "2. Reload GNOME Shell:"
echo "   - On X11: Alt+F2, type 'r', press Enter"
echo "   - On Wayland: Log out and log back in, OR:"
echo "     busctl --user call org.gnome.Shell /org/gnome/Shell org.gnome.Shell Eval s 'Meta.restart(\"Restarting…\")'"
echo ""
echo "3. Open GIMP and watch the menu appear!"
echo ""
echo "View logs with:"
echo "  journalctl -f -o cat /usr/bin/gnome-shell | grep 'Global Menu'"
echo ""
