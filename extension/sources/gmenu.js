// Tier 1: native GMenu, consumed entirely in-process.
//
// GtkApplication windows announce their exported menu/action object paths
// through the gtk_shell1 Wayland protocol (X properties on X11); mutter
// exposes them on MetaWindow. When a menubar path is present we read the
// menu with Gio.DBusMenuModel and drive actions with Gio.DBusActionGroup —
// live structure and state, no daemon round-trip.
//
// Both DBusMenuModel and DBusActionGroup populate asynchronously on first
// use, so fetches wait briefly for items-changed before serializing. An
// exported-but-empty menubar (LibreOffice under GNOME) yields zero menus and
// the caller falls back to the daemon tiers.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

// How long to wait for a lazily-populating model before serving what we have.
const POPULATE_TIMEOUT_MS = 200;

function stripMnemonic(label) {
    // GMenu labels mark the mnemonic with '_' ('__' is a literal underscore).
    return label.replace(/__/g, '\x00').replace(/_/g, '').replace(/\x00/g, '_');
}

export class GMenuSource {
    constructor(metaWindow, onChanged) {
        this._onChanged = onChanged;
        this._generation = 1;
        this._nodes = new Map(); // id -> {model} | {action, target}
        this._nextId = 0;

        const conn = Gio.DBus.session;
        const busName = metaWindow.get_gtk_unique_bus_name();
        this._appId = metaWindow.get_gtk_application_id() ?? '';
        this._menubar = Gio.DBusMenuModel.get(
            conn, busName, metaWindow.get_gtk_menubar_object_path());

        this._groups = new Map();
        const appPath = metaWindow.get_gtk_application_object_path();
        const winPath = metaWindow.get_gtk_window_object_path();
        if (appPath)
            this._groups.set('app', Gio.DBusActionGroup.get(conn, busName, appPath));
        if (winPath)
            this._groups.set('win', Gio.DBusActionGroup.get(conn, busName, winPath));
        // Poke the groups so they subscribe and fill in the background; state
        // is re-read every time a menu opens, so early misses self-correct.
        for (const group of this._groups.values())
            group.list_actions();

        this._rootChangedId = this._menubar.connect('items-changed', () => {
            this._generation++;
            this._onChanged?.();
        });
    }

    destroy() {
        if (this._rootChangedId) {
            this._menubar.disconnect(this._rootChangedId);
            this._rootChangedId = 0;
        }
        this._nodes.clear();
        this._onChanged = null;
    }

    // -- the same interface menubar.js uses on the daemon client ------------

    async getMenuBar() {
        await this._waitForItems(this._menubar);
        this._nodes.clear();
        this._nextId = 0;
        const menus = (await this._serializeLevel(this._menubar))
            .filter(n => n.type === 'submenu' && n.label);
        return {
            source: 'gmenu',
            generation: this._generation,
            app_id: this._appId,
            menus,
        };
    }

    async getChildren(nodeId) {
        const node = this._nodes.get(nodeId);
        if (!node?.model)
            return {generation: this._generation, children: []};
        await this._waitForItems(node.model);
        const children = await this._serializeLevel(node.model);
        return {generation: this._generation, children};
    }

    async activate(_generation, nodeId) {
        // No generation guard needed: node ids resolve to live action names,
        // so a stale id can at worst activate by its (still current) name.
        const node = this._nodes.get(nodeId);
        if (!node?.action) {
            console.warn(`GlobalMenu: gmenu activate on unknown node ${nodeId}`);
            return false;
        }
        const resolved = this._resolveAction(node.action);
        if (!resolved) {
            console.warn(`GlobalMenu: gmenu no action group for ${node.action}`);
            return false;
        }
        resolved.group.activate_action(resolved.name, node.target ?? null);
        return true;
    }

    opened(_nodeId) {}
    closed(_nodeId) {}

    // -- serialization -------------------------------------------------------

    async _serializeLevel(model) {
        const out = [];
        const n = model.get_n_items();
        for (let i = 0; i < n; i++) {
            const section = model.get_item_link(i, 'section');
            if (section) {
                await this._waitForItems(section);
                const items = await this._serializeLevel(section);
                if (items.length > 0) {
                    if (out.length > 0 && out.at(-1).type !== 'separator')
                        out.push({id: this._allocId({}), type: 'separator', label: '', enabled: true});
                    out.push(...items);
                }
                continue;
            }
            const item = this._serializeItem(model, i);
            if (item)
                out.push(item);
        }
        return out;
    }

    _serializeItem(model, i) {
        const rawLabel = this._attr(model, i, 'label');
        const submenu = model.get_item_link(i, 'submenu');
        const label = stripMnemonic(rawLabel ?? '');

        if (submenu) {
            const id = this._allocId({model: submenu});
            return {id, label, type: 'submenu', enabled: true, children: null};
        }

        const action = this._attr(model, i, 'action');
        const target = model.get_item_attribute_value(i, 'target', null);
        const accel = this._attr(model, i, 'accel');
        const state = this._actionState(action, target);
        const id = this._allocId({action, target});
        return {id, label, accel, ...state};
    }

    _actionState(action, target) {
        if (!action)
            return {type: 'item', enabled: false};
        const resolved = this._resolveAction(action);
        // Unknown scope or not-yet-populated group: render optimistically.
        if (!resolved || !resolved.group.has_action(resolved.name))
            return {type: 'item', enabled: true};

        const {group, name} = resolved;
        const enabled = group.get_action_enabled(name);
        const state = group.get_action_state(name);
        if (state) {
            if (state.is_of_type(new GLib.VariantType('b')))
                return {type: 'checkbox', enabled, checked: state.get_boolean()};
            if (target)
                return {type: 'radio', enabled, checked: state.equal(target)};
        }
        return {type: 'item', enabled};
    }

    _resolveAction(action) {
        const dot = action.indexOf('.');
        if (dot < 0)
            return null;
        const group = this._groups.get(action.slice(0, dot));
        return group ? {group, name: action.slice(dot + 1)} : null;
    }

    _attr(model, i, name) {
        const value = model.get_item_attribute_value(i, name, new GLib.VariantType('s'));
        return value?.get_string()[0] ?? null;
    }

    _allocId(node) {
        const id = `g${this._nextId++}`;
        this._nodes.set(id, node);
        return id;
    }

    // -- async population ----------------------------------------------------

    _waitForItems(model) {
        if (model.get_n_items() > 0)
            return Promise.resolve();
        return new Promise(resolve => {
            let signalId = 0;
            const timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POPULATE_TIMEOUT_MS, () => {
                model.disconnect(signalId);
                resolve();
                return GLib.SOURCE_REMOVE;
            });
            signalId = model.connect('items-changed', () => {
                model.disconnect(signalId);
                GLib.source_remove(timeoutId);
                resolve();
            });
        });
    }
}
