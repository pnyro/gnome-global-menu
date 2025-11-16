Short answer: **yes — it’s possible**, but the practical route that avoids hacking Mutter/KWin or the app toolkits is to **build a userspace helper + GNOME Shell extension** that reconstructs menus from accessibility (AT-SPI) or from existing DBus/`dbusmenu` exports. Below I give a concrete, prioritized plan (with tradeoffs), exact building blocks, and small code skeletons you can use to start hacking right away.

Key facts you’ll rely on
- KDE/Plasma uses an “appmenu” Wayland protocol + DBusMenu/exporters to make global menus work in Plasma. That protocol exists and is how Plasma implements Wayland global menus. citeturn0search1turn0search6  
- The historical approach on Linux is `dbusmenu`/`appmenu-gtk-module` + a registrar/proxy that maps window → DBus menu. That works well on X11 but is flaky under Wayland because compositors and toolkits changed. citeturn0search12turn0search9  
- Wayland support is the blocking problem: compositor features (xdg-dbus-annotation, kde-appmenu support) and GTK/Qt export differences have caused Plasma/others to have gaps; bugs and partial implementations mean some apps won’t export menus on Wayland. citeturn0search15turn0search14  
- AT-SPI (the accessibility stack) exposes menubars/menus as accessible objects (MenuBar, Menu, MenuItem). It works on Wayland and is an alternative source of menu structure. Using AT-SPI, you can *scrape* menus and invoke actions programmatically. citeturn1search3turn1search20

Two realistic approaches (ordered by practicality)

1) **AT-SPI scraper + GNOME Shell extension (recommended first) — userspace only**
   - **Why:** Works on Wayland since AT-SPI runs on Wayland, doesn’t require changing Mutter, and can operate on GTK3/Qt apps that expose accessible menu structure. It won’t help GTK4 apps that truly have no menu bar by design, but you already accepted that.
   - **High-level architecture**
     1. **helper daemon** (Python/Rust): subscribe to AT-SPI events, track the active window, extract the MenuBar tree (roles: `MenuBar`, `Menu`, `MenuItem`), serialize it to JSON and expose it over a simple session D-Bus API or a local UNIX socket.
     2. **GNOME Shell extension (GJS)**: small panel item that queries the helper whenever the active window changes, builds a panel menu UI from the JSON, and when a menu item is clicked the extension calls the helper to `doAction()` on the corresponding AT-SPI object (or instructs the helper to activate it).
   - **Pros:** No compositor patching; iterative; you can make it work reasonably well for many GTK3/Qt apps.  
     **Cons:** Depends on apps exposing accessible menus correctly; shortcuts/accelerators mapping might need extra handling; latency and focus edge cases to debug.
   - **Concrete starting pieces**
     - Libraries: `pyatspi` (Python), `python-dbus` or `pydbus` (for IPC), `gobject-introspection` / GJS for extension.  
     - Example pseudo-sketch (Python helper – conceptual):

```python
# conceptual sketch (not production-ready)
import pyatspi
import json
from pydbus import SessionBus

def find_menubar(app_obj):
    # recursively find AT-SPI object with role MenuBar
    # return structured dict {title, children:[...], path_id: "..."}
    pass

def activate_menuitem(path_id):
    # find object by stored path and call obj.doAction(0)
    pass

# expose get_menu_for_window(window_xid) and activate_menuitem via DBus
```

     - Example GJS outline for extension:

```js
/* extension main.js (outline) */
const PanelMenu = imports.ui.panelMenu;
const Main = imports.ui.main;

class GlobalMenu extends PanelMenu.Button {
  _init() {
    super._init(0.0, 'GlobalMenu');
    // UI container, click handlers...
  }
  async _refreshMenu() {
    // call helper over DBus, get JSON, build menu
  }
}

function init() {}
function enable() { this._menu = new GlobalMenu(); Main.panel.addToStatusArea('global-menu', this._menu); }
function disable() { this._menu.destroy(); }
```

   - **Implementation notes & gotchas**
     - Use AT-SPI roles (MenuBar / Menu / MenuItem); menu activation uses `doAction()` on the accessible object. Test with `pyatspi` and `atspi-tools` to inspect objects. citeturn1search9turn1search3  
     - Ensure `at-spi2-core` is running (usual on GNOME). For Qt apps, make sure `qt-at-spi` (or equivalent) is available so Qt menus expose AT-SPI. citeturn1search11
     - Shortcuts: map the `accelerator` property where available; keyboard integration (Alt to focus, mnemonics) needs work.
     - Accessibility objects can move/disappear when menus are open; listen to events and rebuild dynamically.
   - **Why start here:** fastest to prototype, no kernel/compositor hacks, incremental wins.

2) **DBusMenu / kde-appmenu proxy approach (hard)**
   - **Why:** It mirrors Plasma’s design: apps serialize menus over DBus (dbusmenu), and the compositor (or a compositor-capable proxy) exposes per-window menu object paths. KDE added a Wayland protocol for this. citeturn0search1turn0search12
   - **Options to implement**
     - **(A)** Implement the KDE appmenu Wayland protocol in Mutter (native route): you'd need to patch Mutter (Mutter/gnome shell) to accept `kde-appmenu` objects per window and notify a GNOME Shell extension. This is the most correct but requires a compositor patch and upstream acceptance.
     - **(B)** Run a userspace proxy that talks both sides:
       - Have apps export `dbusmenu` (via appmenu-gtk-module / appmenu-qt / dbusmenu exporters). On Wayland the *exposure step* usually requires a compositor protocol (xdg-dbus-annotation or kde-appmenu) — you can try to emulate that by intercepting application startup, reading XDG annotations, or LD_PRELOADing a shim that claims a dbus path and registers it with a “fake registrar” — heavy and fragile.
   - **Why it’s hard now:** Wayland requires a compositor to convey the DBus path (or xdg annotation support to let the app place its object on the bus and the compositor connect it to the surface). Plasma has implemented bits of this stack; other compositors may not. Bugs and partial implementations are the reason global menu on Wayland is spotty. citeturn0search15turn0search14

Which path I’d recommend you attempt first
- **Prototype the AT-SPI approach**. It’s feasible to get a working proof-of-concept in a few days of focused work:
  1. Write a small Python helper using `pyatspi` to print menu trees for the active window, and a small script to `doAction()` on a menuitem. Verify with several target apps (GIMP, LibreOffice, a Qt app).  
  2. Create a GNOME Shell extension skeleton that shows a panel button and displays a JSON menu from the helper. Wire click → helper activate. Iterate until interaction feels right.  
  3. Harden: keyboard navigation, mnemonics, caching, focus/blur handling, and leave a toggle/blacklist for misbehaving apps.
- If you get stuck because a critical app doesn’t expose menu info via AT-SPI, evaluate whether that app has a `dbusmenu` exporter or whether you can write a small plugin/patch for it. Only then consider the compositor / kde-appmenu route.

Useful links and references (for immediate reading)
- KDE appmenu Wayland protocol (protocol description). citeturn0search1  
- DBusMenu reference (properties/format used by appmenu exporters). citeturn0search12  
- Blog / history: using `gmenu-dbusmenu-proxy` + appmenu modules to make GTK apps use Plasma global menu (useful to inspect the proxy idea). citeturn0search9  
- Wayland / KDE Wayland issues and the `xdg-dbus-annotation` dependency that affected support. citeturn0search15turn0search14  
- AT-SPI / GTK accessibility docs (how menus are exposed). citeturn1search3turn1search20

If you want, I can do either of these *right now*:
- produce a small **pyatspi prototype** (helper script) that lists the active window’s MenuBar and shows how to call `doAction()` (quick Python sketch you can run), **and**  
- produce a minimal **GJS GNOME Shell extension skeleton** (main.js + metadata.json) that talks to that helper over session D-Bus.

Tell me which of those you want first (pyatspi helper or extension skeleton) and I will drop a runnable starter in the next message.
