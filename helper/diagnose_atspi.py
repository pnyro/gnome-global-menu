#!/usr/bin/env python3
"""
AT-SPI Diagnostic Tool
Helps identify why applications might not be showing up in AT-SPI.
"""

import subprocess
import sys


def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def check_chromium_browsers():
    """Check if Chromium browsers have accessibility enabled."""
    print_section("Chromium-based Browsers (Chrome, Brave, Edge, etc.)")

    print("Chromium browsers disable AT-SPI by default for performance.")
    print("\nTo enable AT-SPI in Chromium browsers:")
    print("  1. Open the browser")
    print("  2. Go to: chrome://accessibility (or brave://accessibility)")
    print("  3. Enable 'Accessibility' mode")
    print("  4. Alternatively, start browser with: --force-renderer-accessibility")
    print("\nExample:")
    print("  google-chrome --force-renderer-accessibility")
    print("  brave --force-renderer-accessibility")

    print("\n⚠️  Note: This may impact browser performance")


def check_flatpak_atspi():
    """Check flatpak AT-SPI configuration."""
    print_section("Flatpak Applications")

    print("Flatpak apps run in a sandbox and may use a separate AT-SPI bus.")
    print("\nTo check if flatpak has AT-SPI access:")

    try:
        # Check if flatpak is installed
        result = subprocess.run(['flatpak', '--version'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"  ✅ Flatpak installed: {result.stdout.strip()}")
        else:
            print("  ❌ Flatpak not found")
            return
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("  ❌ Flatpak not installed")
        return

    # List flatpak apps
    try:
        result = subprocess.run(['flatpak', 'list', '--app'],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            print("\n  Installed Flatpak apps:")
            for line in result.stdout.strip().split('\n')[:10]:
                print(f"    • {line}")
        else:
            print("  No flatpak apps installed")
    except subprocess.TimeoutExpired:
        print("  ⚠️  Timeout listing flatpak apps")

    print("\n  Flatpak AT-SPI access:")
    print("    • Flatpaks need 'a11y-bus' permission")
    print("    • Some flatpaks may not expose menus even with permission")
    print("    • Native apps are more likely to work with AT-SPI")


def check_gtk4_apps():
    """Info about GTK4 applications."""
    print_section("GTK4 Applications")

    print("Many modern GNOME apps use GTK4 with client-side decorations.")
    print("They often don't have traditional menu bars:")
    print("  ❌ Nautilus (Files) - hamburger menu only")
    print("  ❌ ptyxis - minimal UI")
    print("  ❌ GNOME Console, Text Editor, etc.")
    print("\nThese apps won't work with global menu unless they expose")
    print("their menus via DBusMenu or have a traditional menu bar.")


def check_atspi_daemon():
    """Check if AT-SPI daemon is running."""
    print_section("AT-SPI Daemon Status")

    try:
        result = subprocess.run(['ps', 'aux'],
                              capture_output=True, text=True, timeout=5)
        atspi_processes = [line for line in result.stdout.split('\n')
                          if 'at-spi' in line.lower() and 'grep' not in line]

        if atspi_processes:
            print("✅ AT-SPI daemon is running:")
            for proc in atspi_processes[:5]:
                # Simplify output
                parts = proc.split()
                if len(parts) >= 11:
                    print(f"  • PID {parts[1]}: {' '.join(parts[10:])}")
        else:
            print("❌ AT-SPI daemon not found!")
            print("   Try: sudo systemctl --user start at-spi-dbus-bus.service")
    except subprocess.TimeoutExpired:
        print("⚠️  Timeout checking processes")


def check_environment():
    """Check environment variables."""
    print_section("Environment Variables")

    import os

    vars_to_check = [
        'GTK_MODULES',
        'QT_ACCESSIBILITY',
        'ACCESSIBILITY_ENABLED',
    ]

    found_any = False
    for var in vars_to_check:
        value = os.environ.get(var)
        if value:
            print(f"  {var}={value}")
            found_any = True

    if not found_any:
        print("  No accessibility environment variables set")
        print("\n  To enable Qt accessibility:")
        print("    export QT_ACCESSIBILITY=1")


def main():
    """Run all diagnostics."""
    print("="*70)
    print("  AT-SPI Diagnostic Tool for GNOME Global Menu")
    print("="*70)
    print("\nThis tool helps identify why some applications might not be")
    print("showing up in AT-SPI or exposing menu structures.\n")

    check_atspi_daemon()
    check_chromium_browsers()
    check_flatpak_atspi()
    check_gtk4_apps()
    check_environment()

    print("\n" + "="*70)
    print("  Summary")
    print("="*70)
    print("\nApplications most likely to work:")
    print("  ✅ GIMP (GTK2/3)")
    print("  ✅ LibreOffice")
    print("  ✅ Older GTK3 apps with menu bars")
    print("  ✅ Qt apps with QT_ACCESSIBILITY=1")
    print("\nApplications that need configuration:")
    print("  ⚙️  Chrome/Brave - need --force-renderer-accessibility")
    print("  ⚙️  Flatpak apps - may need native install")
    print("\nApplications that won't work:")
    print("  ❌ Modern GTK4 apps without menu bars")
    print("  ❌ Electron apps without AT-SPI support")
    print("="*70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
