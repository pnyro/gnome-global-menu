// The menubar widget: one container in the panel's left box, one entry per
// top-level menu. Menus are populated lazily on open so state is always
// fresh, and rebuilt in place (no destroy/recreate churn across focus
// changes unless the menu set actually changed).

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const PANEL_POSITION = 1; // in _leftBox, right after Activities

function formatAccel(accel) {
    if (!accel)
        return '';
    return accel
        .replace(/<Primary>|<Control>|<Ctrl>/gi, 'Ctrl+')
        .replace(/<Shift>/gi, 'Shift+')
        .replace(/<Alt>/gi, 'Alt+')
        .replace(/<Super>/gi, 'Super+')
        .replace(/\+(\w)$/, (_, k) => `+${k.toUpperCase()}`);
}

class MenuEntry {
    constructor(node, owner) {
        this.node = node;
        this._owner = owner;

        this.button = new St.Button({
            style_class: 'panel-button global-menu-entry',
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        this.button.set_child(new St.Label({
            text: node.label,
            y_align: Clutter.ActorAlign.CENTER,
        }));

        this.menu = new PopupMenu.PopupMenu(this.button, 0.0, St.Side.TOP);
        this.menu.actor.hide();
        Main.uiGroup.add_child(this.menu.actor);

        // PopupMenu.open() refuses to open an empty menu, so populate before
        // toggling: populateMenu synchronously seeds a loading placeholder,
        // then fills in the real items when the daemon answers.
        this.button.connect('button-press-event', () => {
            if (!this.menu.isOpen)
                this._owner.populateMenu(this.menu, this.node);
            this.menu.toggle();
            return Clutter.EVENT_STOP;
        });
        // macOS behavior: while any menu is open, hovering another top-level
        // entry slides over to it.
        this.button.connect('notify::hover', () => {
            if (this.button.hover)
                this._owner.entryHovered(this);
        });
        // Left/Right at the top menu level move across the bar.
        this.menu.actor.connect('key-press-event', (_actor, event) => {
            const key = event.get_key_symbol();
            if (key === Clutter.KEY_Left)
                return this._owner.switchRelative(this, -1);
            if (key === Clutter.KEY_Right)
                return this._owner.switchRelative(this, 1);
            return Clutter.EVENT_PROPAGATE;
        });
        this.menu.connect('open-state-changed', (_menu, open) => {
            this.button.checked = open;
            this._owner.entryOpenState(this, open);
        });
    }

    open(animate = true) {
        if (this.menu.isOpen)
            return;
        this._owner.populateMenu(this.menu, this.node);
        this.menu.open(animate);
    }

    destroy() {
        this.menu.destroy();
        this.button.destroy();
    }
}

export class GlobalMenuBar {
    constructor(settings = null) {
        this._settings = settings;
        this._source = null; // whoever produced the current model (daemon client or GMenuSource)
        this._entries = [];
        this._generation = 0;
        this._openEntry = null;

        this._box = new St.BoxLayout({style_class: 'global-menu-bar'});
        Main.panel._leftBox.insert_child_at_index(this._box, PANEL_POSITION);
    }

    get source() {
        return this._source;
    }

    get generation() {
        return this._generation;
    }

    get roots() {
        return this._entries.map(e => e.node);
    }

    get anchorActor() {
        return this._box;
    }

    // -- top-level interaction ----------------------------------------------

    entryOpenState(entry, open) {
        if (open)
            this._openEntry = entry;
        else if (this._openEntry === entry)
            this._openEntry = null;
    }

    entryHovered(entry) {
        if (this._openEntry && this._openEntry !== entry)
            entry.open(false); // menuManager closes the previous one
    }

    switchRelative(entry, direction) {
        const i = this._entries.indexOf(entry);
        if (i < 0 || this._entries.length < 2)
            return Clutter.EVENT_PROPAGATE;
        const next = this._entries[(i + direction + this._entries.length) % this._entries.length];
        next.open(false);
        return Clutter.EVENT_STOP;
    }

    openFirst() {
        this._entries[0]?.open(true);
    }

    setModel(model, source) {
        this._source = source ?? null;
        const menus = model?.menus ?? [];
        if (model && model.generation === this._generation && menus.length === this._entries.length)
            return; // same extraction; keep widgets (open menus stay open)

        this._generation = model?.generation ?? 0;

        // Same top-level labels (a re-extraction of the same menubar): keep
        // the widgets — an open menu must not slam shut — and just rebind the
        // node ids, which may have changed with the new generation.
        if (menus.length === this._entries.length && this._entries.length > 0 &&
            menus.every((node, i) => node.label === this._entries[i].node.label)) {
            for (let i = 0; i < menus.length; i++)
                this._entries[i].node = menus[i];
            return;
        }

        this._removeEntries();

        for (const node of menus) {
            const entry = new MenuEntry(node, this);
            this._entries.push(entry);
            this._box.add_child(entry.button);
            Main.panel.menuManager.addMenu(entry.menu);
        }
        this._box.visible = this._entries.length > 0;
    }

    clear() {
        this._source = null;
        this._generation = 0;
        this._removeEntries();
        this._box.visible = false;
    }

    async populateMenu(menu, node) {
        const source = this._source;
        if (!source)
            return;
        menu.removeAll();
        const loading = new PopupMenu.PopupMenuItem('…', {reactive: false});
        menu.addMenuItem(loading);

        source.opened(node.id);
        let children;
        try {
            ({children} = await source.getChildren(node.id));
        } catch (e) {
            console.warn(`GlobalMenu: fetching ${node.label} failed: ${e.message}`);
            children = [];
        }
        console.log(`GlobalMenu: populate '${node.label}': ${children?.length ?? 0} items (still open=${menu.isOpen})`);
        if (!menu.isOpen)
            return; // closed while we were fetching
        menu.removeAll();
        this._buildItems(menu, children ?? []);
    }

    _buildItems(menu, nodes) {
        for (const node of nodes) {
            if (node.type === 'separator') {
                menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                continue;
            }
            if (node.type === 'submenu') {
                const sub = new PopupMenu.PopupSubMenuMenuItem(node.label);
                sub.setSensitive(node.enabled !== false);
                // Seed: PopupSubMenu.open() also refuses to expand when empty.
                sub.menu.addMenuItem(new PopupMenu.PopupMenuItem('…', {reactive: false}));
                let loadedOpenCount = 0;
                sub.menu.connect('open-state-changed', async (_m, open) => {
                    if (!open || !this._source)
                        return;
                    const thisOpen = ++loadedOpenCount;
                    this._source.opened(node.id);
                    try {
                        const {children} = await this._source.getChildren(node.id);
                        if (!sub.menu.isOpen || thisOpen !== loadedOpenCount)
                            return;
                        sub.menu.removeAll();
                        this._buildItems(sub.menu, children ?? []);
                        sub.menu.open(true);
                    } catch (e) {
                        console.warn(`GlobalMenu: submenu ${node.label} failed: ${e.message}`);
                    }
                });
                menu.addMenuItem(sub);
                continue;
            }

            const item = new PopupMenu.PopupMenuItem(node.label);
            if (node.enabled === false)
                item.setSensitive(false);
            if (node.type === 'checkbox')
                item.setOrnament(node.checked ? PopupMenu.Ornament.CHECK : PopupMenu.Ornament.NONE);
            else if (node.type === 'radio')
                item.setOrnament(node.checked ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);

            const accel = this._settings?.get_boolean('show-accels') !== false
                ? formatAccel(node.accel) : '';
            if (accel) {
                item.label.x_expand = true;
                item.add_child(new St.Label({
                    text: accel,
                    style_class: 'global-menu-accel',
                    y_align: Clutter.ActorAlign.CENTER,
                }));
            }

            item.connect('activate', () => {
                this._source?.activate(this._generation, node.id).catch(e =>
                    console.warn(`GlobalMenu: activate failed: ${e.message}`));
            });
            menu.addMenuItem(item);
        }

        if (nodes.length === 0)
            menu.addMenuItem(new PopupMenu.PopupMenuItem('(empty)', {reactive: false}));
    }

    _removeEntries() {
        for (const entry of this._entries) {
            Main.panel.menuManager.removeMenu(entry.menu);
            this._box.remove_child(entry.button);
            entry.destroy();
        }
        this._entries = [];
    }

    destroy() {
        this._removeEntries();
        Main.panel._leftBox.remove_child(this._box);
        this._box.destroy();
        this._box = null;
    }
}
