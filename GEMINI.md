# GEMINI Code Assistant Project Context

This document provides context for the "GNOME Global Menu" project, intended for use by the Gemini Code Assistant.

## Project Overview

This project implements a macOS-style global menu bar for the GNOME Shell. It consists of two main components:

1.  **Helper Daemon (`helper/`)**: A Python-based service that runs in the background. It uses the Accessibility Toolkit (AT-SPI) to find the menu bar of the currently focused application, extracts the menu structure, and exposes it over a D-Bus interface.
2.  **GNOME Shell Extension (`extension/`)**: A JavaScript (GJS) extension that adds a new element to the GNOME Shell's top panel. It connects to the helper's D-Bus service, retrieves the menu structure, and dynamically builds and displays the application's menu in the panel.

The two components communicate via D-Bus, with the helper acting as a server and the extension as a client. This architecture allows for a clean separation of concerns and works on both X11 and Wayland.

**Technologies Used:**

*   **Python 3**: For the helper daemon.
*   **PyGObject, `python3-dbus`, `pyatspi`**: Python libraries for D-Bus and accessibility services.
*   **JavaScript (GJS)**: For the GNOME Shell extension.
*   **D-Bus**: For inter-process communication.
*   **AT-SPI**: For accessibility and menu scraping.

## Building and Running

### 1. Install Dependencies

The project requires Python dependencies for the helper service. These can be installed using the system's package manager. For example, on Fedora:

```bash
sudo dnf install python3-pyatspi python3-dbus python3-gobject
```

### 2. Run the Helper Daemon

The helper daemon must be running for the extension to work.

```bash
cd helper
python3 globalmenu_service.py
```

### 3. Install and Enable the Extension

The extension can be installed with the provided script.

```bash
cd extension
./install.sh
```

After installation, you need to restart the GNOME Shell.

*   **On X11**: Press `Alt+F2`, type `r`, and press Enter.
*   **On Wayland**: Log out and log back in.

You can then enable the extension using the GNOME Extensions application or via the command line:

```bash
gnome-extensions enable globalmenu@gnome-shell-extensions
```

### Testing

To test the extension, run an application with a traditional menu bar, such as GIMP.

1.  Start the helper daemon.
2.  Ensure the extension is enabled.
3.  Launch GIMP.
4.  The GIMP menu should appear in the top panel.

## Development Conventions

*   The Python helper follows standard Python conventions. It uses `dbus.service` to create the D-Bus service and `pyatspi` to interact with the accessibility tree.
*   The GNOME Shell extension is written in GJS and follows the standard structure for a GNOME Shell extension. It uses `PanelMenu.Button` to create the top-level menu items and `PopupMenu` for the sub-menus.
*   Communication between the two components is strictly via the D-Bus interface defined in `extension/extension.js` and implemented in `helper/globalmenu_service.py`.
*   Logging in the extension is done via the global `log()` function, and logs can be viewed with `journalctl -f /usr/bin/gnome-shell`.
*   The helper service prints logs directly to the console.
