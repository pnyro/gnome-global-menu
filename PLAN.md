# GNOME Global Menu — Implementation Plan

Goal: the best-in-class global menu for GNOME on Wayland. One renderer in the
panel, one normalized menu model, fed by tiered sources in fidelity order.
Non-libadwaita apps (real menubars: GTK3, Qt, Electron, LibreOffice, GIMP,
Inkscape…) are the core product. A synthetic tier for libadwaita apps is an
optional, off-by-default extra.

Several claims below were verified live on this machine (2026-07-05, Fedora,
GNOME, gnome-text-editor): app-level `org.gtk.Actions` are exported but
window-level groups are empty; the GTK4 AT-SPI tree is anonymous panels (no
menus, no buttons); menu models and the shortcuts dialog are extractable from
the app binary's embedded GResource; GSettings are externally readable and
writable with live effect.

---

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  GNOME Shell Extension (GJS) — "the renderer"                │
│  • Focus tracking (global.display.focus_window — authoritative) │
│  • MenuBar widget in panel + menu search overlay             │
│  • Tier 1 source: native GMenu (consumed in-process)         │
│  • Client for daemon tiers (2, 3, 4)                         │
│  • Accelerator injection (Clutter virtual keyboard)          │
└───────────────┬──────────────────────────────────────────────┘
                │ D-Bus  org.gnome.GlobalMenu (normalized JSON)
┌───────────────▼──────────────────────────────────────────────┐
│  Helper Daemon (Python, systemd user service) — "the sources"│
│  • Tier 2: com.canonical.AppMenu.Registrar (Qt/DBusMenu)     │
│  • Tier 3: AT-SPI scraper (lazy, event-aware)                │
│  • Tier 4 (optional): synthetic libadwaita source            │
│  • Normalizes all sources into one schema                    │
└──────────────────────────────────────────────────────────────┘
```

### Tier selection (per focused window, first match wins)

| Tier | Source | Coverage | Fidelity |
|------|--------|----------|----------|
| 1 | Native GMenu (`org.gtk.Menus`) | GTK3/GTK4 apps calling `gtk_application_set_menubar` | Perfect: live structure, enabled/toggle state |
| 2 | DBusMenu via our AppMenu Registrar | Qt apps (auto-export when registrar exists), libdbusmenu apps | Perfect: live state, icons, accels |
| 3 | AT-SPI scraping | GTK3, Qt, Electron, LibreOffice, Java — incl. Flatpaks (a11y bus crosses the sandbox) | Good: structure + accels; state refreshed on open |
| 4 | Synthetic (optional, off by default) | libadwaita / hamburger-only apps | Static structure; activation via bus actions + key injection |

Key design decisions carried through everything below:

- **Focus tracking lives in the extension.** `global.display.focus_window` +
  `Shell.WindowTracker` are authoritative. This deletes the AT-SPI
  `window:activate` path and with it the `mutter-x11-frames` / `gnome-shell`
  phantom-focus hacks. The extension tells the daemon what to serve.
- **One schema, one renderer.** The extension renders normalized JSON and
  never knows which tier produced it. Tier 1 is normalized inside the
  extension; tiers 2–4 inside the daemon.
- **Lazy everywhere.** Focus change fetches top-level labels only; children
  are fetched when a menu opens. Activation is generation-tagged so a stale
  UI can never trigger the wrong item.
- **Daemon is a service, not a script.** systemd user unit + D-Bus
  activation; the extension watches bus-name ownership and degrades to
  tier 1 only if the daemon dies.

### Normalized menu schema (JSON)

```jsonc
{
  "source": "gmenu | dbusmenu | atspi | synthetic",
  "generation": 42,          // monotonic; bumped on every re-extraction
  "app_id": "org.gimp.GIMP",
  "menus": [                  // top-level menubar entries
    {
      "id": "n17",           // stable within a generation
      "label": "_File",      // '_' marks mnemonic
      "type": "submenu",     // item | submenu | separator | checkbox | radio
      "enabled": true,
      "checked": false,       // checkbox/radio only
      "accel": "<Control>n", // GTK accelerator string, optional
      "children": null        // null = not yet loaded (lazy); [] = empty
    }
  ]
}
```

### D-Bus protocol (daemon interface `org.gnome.GlobalMenu`)

```
SetActiveWindow(a{sv} info)          // extension → daemon on focus change:
                                     // pid, app_id, title, x11-window-id (if XWayland)
GetMenuBar() → s                     // top level of current window's menu (JSON)
GetChildren(s node_id) → s           // lazy fetch; also refreshes that node's state
Activate(u generation, s node_id) → b
Opened(s node_id) / Closed(s node_id)  // hover/open hints (dbusmenu AboutToShow, atspi refresh)
signal MenuUpdated(u generation, s node_id)  // structure/state changed; "" = whole bar
signal MenuBarChanged(u generation)  // new menubar for current window
GetDiagnostics() → a{sv}             // tier chosen, timings, per-app stats
```

Versioned (`Version` property) so extension and daemon can evolve
independently. All calls async on the extension side; nothing ever blocks the
compositor.

### Repository layout (target)

```
extension/
  extension.js          // lifecycle, focus tracker, tier arbitration
  menubar.js            // MenuBar widget + cascading popups
  search.js             // menu search overlay
  sources/gmenu.js      // tier 1: Gio.DBusMenuModel + Gio.DBusActionGroup
  sources/daemon.js     // client for tiers 2/3/4
  keyInjector.js        // Clutter virtual keyboard (used by tier 4 + accel hints)
  prefs.js              // Adw preferences window
  schemas/…             // GSettings schema for extension settings
daemon/
  globalmenu/
    __main__.py         // entry point, GLib loop, GDBus service
    service.py          // org.gnome.GlobalMenu implementation, tier routing
    model.py            // normalized schema types + serialization
    sources/atspi.py    // tier 3
    sources/registrar.py// tier 2 (AppMenu.Registrar + dbusmenu client)
    sources/synthetic/  // tier 4 (optional): gresource.py, uiparse.py, actions.py, gsettings.py
  pyproject.toml
data/
  org.gnome.GlobalMenu.service       // D-Bus activation
  gnome-globalmenu.service           // systemd user unit
Makefile                              // install/uninstall both components
docs/PLAN.md (this file), ARCHITECTURE.md
```

Deleted: `helper/window_tracker.py` (prototype superseded by extension focus
tracking), `helper/globalmenu_service.py` and `helper/menu_serializer.py`
(logic absorbed into `daemon/globalmenu/`), ad-hoc test scripts (replaced by
real tests). Code health rules for everything new: no bare `except:`,
`logging` module instead of emoji prints, Gio/GDBus instead of legacy
`dbus-python`, type hints in the daemon.

---

## 2. Part One — Core (non-libadwaita apps)

### M1 — Foundation: focus tracking, protocol, renderer skeleton, lifecycle

The restructuring milestone. No new menu sources yet; the existing AT-SPI
extraction is wrapped behind the new protocol so the system stays demoable.

- Extension: focus tracker on `notify::focus-window` (debounced ~50 ms to
  swallow focus churn), app identity via `Shell.WindowTracker`
  (`app_id`, PID, XWayland window id when present). Calls `SetActiveWindow`.
- Extension: `MenuBar` widget — a single panel child (left box, after
  Activities) holding all top-level entries. Rebuild-in-place (diff labels)
  instead of destroy/recreate to kill flicker. Proper teardown in
  `disable()` (every signal disconnected, every actor destroyed). Modern
  APIs only (`console.log`, ESM) — EGO-review clean.
- Daemon: new package layout, GDBus service with the protocol above,
  generation counter, systemd unit + D-Bus activation files, Makefile
  install. Extension watches name owner: auto-starts daemon via D-Bus
  activation, degrades gracefully when absent.
- Wire the *existing* scraper in as a temporary tier-3 source behind
  `GetMenuBar`/`GetChildren` (eager under the hood for now).

Accept when: focused-app menus appear/disappear correctly across app
switches, workspaces, and overview; no phantom-focus hacks left; daemon
restarts are survived; extension enable/disable cycles leak nothing.

### M2 — Tier 3 rebuilt: lazy, correct, fast AT-SPI scraping

- Locate the app's accessible by **PID match** on the a11y bus (we know the
  PID from the extension — no more guessing from focus events).
- On focus: find menubar, serialize *top-level labels only*. On `Opened`
  (or `GetChildren`): fetch that menu's children one level deep, including
  enabled/checked state and accelerators — this makes stale-state impossible
  at the moment the user looks at it. Cache subtrees per (app PID,
  menu node); invalidate on `object:children-changed` /
  `object:state-changed` AT-SPI events for nodes we've served, else on TTL.
- Generation-tagged activation: `Activate` validates generation; on
  mismatch, re-resolve by label path before giving up.
- Timeout budget per AT-SPI call batch (e.g. 200 ms) with partial results —
  a hung app yields a truncated menu, never a hung daemon.
- Menubar-hunting heuristics: bounded BFS (not DFS) so shallow menubars are
  found fast in huge trees; skip known-bad roles; per-app blocklist setting.

Accept when: GIMP and LibreOffice window-switch feels instant (<50 ms to
top-level render); opening any menu shows current enabled/checked state;
Electron app (e.g. VS Code/Slack) menus work; a deliberately SIGSTOPped app
degrades to truncated menus without freezing anything.

### M3 — Tier 2: AppMenu Registrar (free Qt coverage)

- Daemon claims `com.canonical.AppMenu.Registrar` and implements
  `RegisterWindow(windowId, menuObjectPath)` / `UnregisterWindow` /
  `GetMenuForWindow`. Track registrations by **sender bus name + PID**
  (queried from the bus), not just X window id — this is what makes Wayland
  matching workable.
- DBusMenu client: consume `com.canonical.dbusmenu` (GetLayout,
  AboutToShow, Event, ItemsPropertiesUpdated, LayoutUpdated), normalize to
  our schema. Live updates map to `MenuUpdated` signals. `Opened` hint →
  `AboutToShow` so Qt apps populate dynamic menus.
- Window→menu matching: XWayland Qt apps match by X window id (extension
  supplies it); native-Wayland Qt apps match by PID.
- **Spike (time-boxed):** verify which Qt platform-theme conditions make Qt
  export menus under GNOME Wayland (registrar presence alone vs.
  `QT_QPA_PLATFORMTHEME=kde` / qt6ct). Outcome documented; if an env nudge
  is required, ship an optional `environment.d` snippet the installer offers,
  and tier 3 remains the automatic fallback for unconfigured Qt apps.
  **Spike outcome (2026-07-06, Fedora 44):** registrar presence alone is
  sufficient — VLC 3 (Qt5, XWayland) exported and registered with no env
  changes the moment it started with the registrar on the bus. Two findings
  to carry forward: (a) Qt does *not* re-register when the registrar name
  changes owner, so a daemon restart orphans running Qt apps until app
  restart (possible fix: read `_KDE_NET_WM_APPMENU_*` X properties for
  XWayland windows); (b) VLC regenerates dbusmenu item ids on every
  AboutToShow and emits Layout/ItemsPropertiesUpdated storms in response to
  our own calls — the daemon must only re-claim on *root* layout changes and
  must not hard-reject activations on generation mismatch alone (ids are
  validated instead; children are refetched fresh at every open anyway).
  Qt6/KDE apps still untested for export (Dolphin hides its QMenuBar by
  default, so it exports nothing).
- Arbitration: registrar-registered window beats AT-SPI for that window.

Accept when: a Qt app (Kdenlive/qBittorrent/VLC) shows full native menus
with live enable/disable and icons-capable data, its in-window menubar
hides itself, and unregistering (app quit) cleans up.

### M4 — Tier 1: native GMenu, entirely in-extension

- On focus, read `MetaWindow.get_gtk_menubar_object_path()` +
  `get_gtk_app_menu_object_path()` + unique bus name (works on Wayland via
  the `gtk_shell1` protocol). If present: build
  `Gio.DBusMenuModel(connection, bus_name, path)` and
  `Gio.DBusActionGroup` for `app.` and `win.` scopes; render directly.
  `items-changed` gives live structure; action `enabled`/`state` gives live
  ornaments. No daemon round-trip at all.
- Normalize into the same in-extension model objects the renderer uses for
  daemon tiers (the renderer stays source-blind).
- Arbitration order finalized: gtk paths present → tier 1; else registrar
  hit → tier 2; else tier 3; else (if enabled) tier 4; else hide bar.

Accept when: a `set_menubar` app (e.g. current GIMP 3.x builds, gedit with
menubar, Inkscape where applicable) renders with instant live state and
works with the daemon stopped.

### M5 — Best-in-class renderer polish + menu search

- **Menubar behavior:** click opens; while open, hovering another top-level
  entry slides to it (macOS behavior); Left/Right arrows move across
  menus, Up/Down within, Enter activates, Esc closes; F10 opens first menu.
- **Cascading submenus:** replace Shell's accordion `PopupSubMenuMenuItem`
  with side-attached cascades (custom `BoxPointer` popups, St widgets) —
  deep GIMP/LibreOffice trees must feel like real menus.
- **Item fidelity:** right-aligned accelerator labels, check/radio
  ornaments that update live (tiers 1–2) or on reopen (tier 3), mnemonic
  underlines, disabled styling, icons where the source provides them
  (dbusmenu).
- **Menu search (the differentiator):** a keybinding (default
  `Super+Shift+/`, configurable) opens a search overlay scoped to the
  focused app; triggers full-depth fetch (parallel, budgeted); fuzzy match
  over item labels; results show full path ("Image ▸ Transform ▸ Flip
  Horizontal") + accel; Enter activates through the same generation-safe
  path. Cache warm trees per app so second invocation is instant.
- **Settings & prefs UI (Adw):** per-tier enable toggles, app blocklist,
  show-accels toggle, search keybinding, panel position/max-width with
  ellipsizing overflow (»-style overflow menu for narrow screens).
- **Panel integration polish:** hide when focused window has no menu
  (option: show app name button instead), don't fight with Activities hot
  corner, handle fullscreen apps.

Accept when: side-by-side with macOS the interaction feels equivalent;
search finds and activates a deep GIMP item in under a second; a GNOME
Shell reviewer would find nothing objectionable in enable/disable hygiene.

### Cross-cutting (spans M1–M5)

- **Testing:** daemon unit tests (schema, normalizers, registrar) with faked
  AT-SPI/dbusmenu objects (pytest); a scriptable integration harness that
  launches real apps and asserts over the D-Bus protocol; extension tested
  in a nested session (`dbus-run-session gnome-shell --devkit`
  / `--nested`). A `make check` that runs what CI can run headless.
- **Docs:** README rewrite (architecture, tier table, install), ARCHITECTURE.md
  (protocol + schema reference), troubleshooting guide (a11y bus, Qt env).
- **Packaging:** `make install` handles both components; extension zip
  target for extensions.gnome.org submission.

---

## 3. Part Two — Optional libadwaita tier (tier 4, off by default)

Everything here is opt-in (global toggle + per-app allowlist), clearly
labeled experimental, and layered so it cannot destabilize tiers 1–3.
Verified foundation: menu models, labels, action names, and accelerators are
recoverable from app binaries' GResources; app-level actions are
bus-activatable; the rest are reachable by synthesizing their accelerator
from the compositor.

### M6a — Static extraction pipeline (daemon, `sources/synthetic/`)

- **GResource reader:** locate the app binary from PID (`/proc/PID/exe`;
  for Flatpaks resolve inside `/var/lib/flatpak/app/…/files/` or via
  `/proc/PID/root`), scan ELF sections for `.gresource*` (section name
  varies — Text Editor uses `.gresource.editor`), extract with
  objcopy-equivalent (pure-Python ELF read, no binutils dependency), load
  via `Gio.Resource`. Also check standalone `.gresource` files in the app
  prefix. Cache by (binary path, mtime).
- **UI parser:** from all `.ui` resources, harvest (a) `<menu>` models —
  labels, action names, accels, stateful targets (the hamburger:
  `primary_menu_model` etc.) and (b) `GtkShortcuts*`/`AdwShortcuts*`
  dialogs — {section → [{title, accelerator}]}.
- **Menu synthesis:** hamburger menu(s) become the primary structure
  (labels + mnemonics preserved); shortcuts-dialog sections contribute
  entries not already covered, grouped under their section titles
  ("Documents", "Zoom", …). Deduplicate by accel/action.

### M6b — Activation resolution (extension + daemon)

Per item, in order:
1. **Exported action:** if the action is `app.`-scoped and present in the
   app's `org.gtk.Actions` (verified live), activate over the bus; stateful
   targets supported. Enabled state readable for these.
2. **Accelerator injection:** otherwise, if the item has an accel, the
   extension replays it into the focused window with a Clutter virtual
   keyboard device (compositor-side; Wayland-native). Guard rails: only
   when the target window is focused, never for bare unmodified keys.
3. Otherwise render the item disabled.

### M6c — Optional GSettings "Preferences" submenu (sub-option of tier 4)

- Map the app id to its GSettings schema; expose booleans and enums as a
  synthetic Preferences submenu with labels from schema summaries; writes
  via `Gio.Settings` (apps apply live — verified). Read-only allowlist of
  safe key types; no keys with side effects beyond the app.

### M6 limitations, stated upfront

- Static: no live enabled/disabled/checked state except bus-exported
  `app.*` actions; contents reflect app defaults, not runtime state
  (e.g. a "Save" that's meaningless with no document is still shown).
- Per-app variance: resource layout/section names differ; parser must fail
  soft (no menu > wrong menu) and log diagnostics; ship tested against a
  starter set (Text Editor, Calculator, Files, Calendar) with a
  compatibility list users can extend.
- Key injection is powerful; it stays off unless tier 4 is enabled, is
  rate-limited, and is auditable in logs. (Also the likeliest EGO review
  concern — one more reason this tier is optional and isolated.)

Accept when: with tier 4 enabled, Text Editor shows a synthesized menubar
(hamburger structure + "Documents/Zoom/…" groups), "New Window" activates
via `app.new-window`, "Save As" lands via `<Control><Shift>s` injection,
and disabling the tier removes all of it with zero residue.

---

## 4. Build order and risk register

Order: **M1 → M2 → M3 → M4 → M5**, then optionally **M6a → M6b → M6c**.
Each milestone leaves the system working end-to-end; M1 and M2 restructure
the existing code rather than discarding it.

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Qt-on-Wayland doesn't auto-export to registrar without env nudge | Tier 2 coverage shrinks | M3 spike; optional environment.d snippet; tier 3 fallback always on |
| `get_gtk_menubar_object_path` API drift across Shell versions | Tier 1 breaks on upgrade | Version-gate; feature-detect; tiers 2/3 unaffected |
| AT-SPI perf on pathological apps | Laggy menus | Lazy fetch + budgets + partial results + blocklist (M2 design) |
| Custom cascading popups fight Shell internals | UI glitches | Build on BoxPointer/PopupMenu primitives; fall back to accordion style per-setting |
| GResource section variance / packed apps (snap) | Tier 4 misses apps | Fail-soft parser, compatibility list, cache negative results |
| EGO review friction (key injection, panel surgery) | Distribution delay | Injection isolated to optional tier; core uses sanctioned APIs only |

Non-goals (explicit): X11-only property paths (tier 1 supersedes), GTK
module injection (`unity-gtk-module`), patched mutter, synthesizing menus
from raw action names without labels, and any support burden for apps with
genuinely no menu and no shortcuts data.
