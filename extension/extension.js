// GNOME Global Menu — shell extension entry point.
// Owns focus tracking (the compositor knows the focused window
// authoritatively) and drives the renderer; menu data comes from the helper
// daemon (AT-SPI / registrar tiers) or, later, native GMenu in-process.

import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {DaemonClient} from './sources/daemon.js';
import {GMenuSource} from './sources/gmenu.js';
import {GlobalMenuBar} from './menubar.js';
import {MenuSearch} from './search.js';

const FOCUS_DEBOUNCE_MS = 60;

const TRACKED_WINDOW_TYPES = [
    Meta.WindowType.NORMAL,
    Meta.WindowType.DIALOG,
    Meta.WindowType.MODAL_DIALOG,
];

export default class GlobalMenuExtension extends Extension {
    enable() {
        this._gmenu = null;
        this._client = new DaemonClient({
            // Daemon signals only drive the UI while a daemon tier is active;
            // tier 1 (gmenu) renders without the daemon entirely.
            onMenuBarChanged: () => {
                if (!this._gmenu)
                    this._refresh();
            },
            onOwnerChanged: owned => {
                if (owned)
                    this._onFocusChanged();
                else if (!this._gmenu)
                    this._menubar?.clear();
            },
        });
        this._settings = this.getSettings();
        this._menubar = new GlobalMenuBar(this._settings);
        this._search = new MenuSearch(this._menubar);

        Main.wm.addKeybinding('menu-search', this._settings,
            Meta.KeyBindingFlags.NONE, Shell.ActionMode.NORMAL,
            () => this._search?.toggle());
        Main.wm.addKeybinding('open-first-menu', this._settings,
            Meta.KeyBindingFlags.NONE, Shell.ActionMode.NORMAL,
            () => this._menubar?.openFirst());

        this._focusId = global.display.connect('notify::focus-window',
            () => this._onFocusChanged());
        this._debounceId = 0;
        this._refreshing = false;
        this._onFocusChanged();
    }

    disable() {
        if (this._debounceId) {
            GLib.source_remove(this._debounceId);
            this._debounceId = 0;
        }
        if (this._focusId) {
            global.display.disconnect(this._focusId);
            this._focusId = 0;
        }
        Main.wm.removeKeybinding('menu-search');
        Main.wm.removeKeybinding('open-first-menu');
        this._search?.destroy();
        this._search = null;
        this._menubar?.destroy();
        this._menubar = null;
        this._dropGMenu();
        this._client?.destroy();
        this._client = null;
        this._settings = null;
    }

    _onFocusChanged() {
        if (this._debounceId)
            GLib.source_remove(this._debounceId);
        this._debounceId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, FOCUS_DEBOUNCE_MS, () => {
            this._debounceId = 0;
            this._sendFocus().catch(e =>
                console.warn(`GlobalMenu: focus update failed: ${e.message}`));
            return GLib.SOURCE_REMOVE;
        });
    }

    async _sendFocus() {
        const info = this._focusedWindowInfo();
        if (info === null)
            return; // popup/OSD/etc: keep the current menu

        // Tier 1: the window exports a native GMenu menubar — consume it
        // in-process, no daemon involved. An exported-but-empty menubar
        // (LibreOffice under GNOME) falls through to the daemon tiers.
        const win = global.display.focus_window;
        if (win?.get_gtk_menubar_object_path?.() && win.get_gtk_unique_bus_name?.()) {
            this._dropGMenu();
            const gmenu = new GMenuSource(win, () => this._refreshGMenu());
            this._gmenu = gmenu;
            const bar = await gmenu.getMenuBar();
            if (this._gmenu !== gmenu)
                return; // focus moved on while the model populated
            if (bar.menus.length > 0) {
                console.log(`GlobalMenu: tier-1 gmenu for ${info.appId}: ${bar.menus.length} menus`);
                this._menubar?.setModel(bar, gmenu);
                // Let the daemon drop its claim on the previous window.
                this._client.setActiveWindow({pid: 0}).catch(() => {});
                return;
            }
            console.log(`GlobalMenu: exported menubar empty for ${info.appId}, falling back to daemon`);
        }
        this._dropGMenu();

        await this._client.setActiveWindow(info);
        await this._refresh();
    }

    _dropGMenu() {
        this._gmenu?.destroy();
        this._gmenu = null;
    }

    async _refreshGMenu() {
        const gmenu = this._gmenu;
        if (!gmenu)
            return;
        const bar = await gmenu.getMenuBar();
        if (this._gmenu === gmenu && bar.menus.length > 0)
            this._menubar?.setModel(bar, gmenu);
    }

    _focusedWindowInfo() {
        const win = global.display.focus_window;
        // No focused window (overview, desktop): keep the last app's menu,
        // macOS-style. The daemon detects dead apps on its own.
        if (!win)
            return null;
        if (!TRACKED_WINDOW_TYPES.includes(win.get_window_type()))
            return null;

        const app = Shell.WindowTracker.get_default().get_window_app(win);
        let xid = 0;
        try {
            xid = win.get_xwindow?.() ?? 0;
        } catch {
            xid = 0;
        }
        if (!xid) {
            // mutter 46+ dropped get_xwindow() from the public API; X11
            // windows still lead their description with the xid ("0x%lx (%s)").
            const m = win.get_description?.()?.match(/^0x[0-9a-fA-F]+/);
            if (m)
                xid = parseInt(m[0], 16);
        }
        return {
            pid: win.get_pid?.() ?? 0,
            appId: app?.get_id() ?? '',
            title: win.get_title() ?? '',
            xid,
        };
    }

    async _refresh() {
        if (this._refreshing)
            return;
        this._refreshing = true;
        try {
            const bar = await this._client.getMenuBar();
            if (!this._gmenu)
                this._menubar?.setModel(bar, this._client);
        } finally {
            this._refreshing = false;
        }
    }
}
