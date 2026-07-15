// The menubar widget: one container in the panel's left box, one entry per
// top-level menu. Menus are populated lazily on open so state is always
// fresh, and rebuilt in place (no destroy/recreate churn across focus
// changes unless the menu set actually changed).

import Clutter from 'gi://Clutter';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const PANEL_POSITION = 1; // in _leftBox, right after Activities

// Turn an app id ("org.qbittorrent.qBittorrent.desktop") into a display name
// ("qBittorrent"), preferring the desktop entry's own name when resolvable.
function appDisplayName(appId) {
    if (!appId)
        return '';
    const app = Shell.AppSystem.get_default().lookup_app(appId) ??
        Shell.AppSystem.get_default().lookup_app(`${appId}.desktop`);
    if (app)
        return app.get_name();
    return appId.replace(/\.desktop$/, '').split('.').at(-1) ?? appId;
}

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

// Non-reactive AND non-focusable: keyboard navigation may land focus on a
// focusable placeholder (PopupSubMenuMenuItem's Right-arrow handler navigates
// into the submenu the moment it opens), and destroying the focused actor on
// rebuild drops key focus on the floor — arrows and Space go dead until the
// mouse re-establishes focus.
function loadingItem(text = '…') {
    return new PopupMenu.PopupMenuItem(text, {reactive: false, can_focus: false});
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
        // Scope class so the spacious item styling only hits our dropdowns,
        // not every popup menu in the shell.
        this.menu.actor.add_style_class_name('global-menu-popup');
        this.menu.actor.hide();
        Main.uiGroup.add_child(this.menu.actor);

        // Keep the menu seeded: PopupMenu.open() refuses to open an empty
        // menu, and the menu manager's built-in hover-switching (slide to
        // another entry while one is open) calls open() directly — with an
        // empty menu it dies silently. Populating on open-state-changed
        // (below) then covers every opener: click, keyboard, hover-switch.
        this.menu.addMenuItem(loadingItem());

        this.button.connect('button-press-event', () => {
            this.menu.toggle();
            return Clutter.EVENT_STOP;
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
            if (open)
                this._owner.populateMenu(this.menu, this.node);
        });
    }

    open(animate = true) {
        if (!this.menu.isOpen)
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

        this._box = new St.BoxLayout({style_class: 'global-menu-bar'});
        this._title = new St.Label({
            style_class: 'global-menu-title',
            y_align: Clutter.ActorAlign.CENTER,
            visible: false,
        });
        this._box.add_child(this._title);
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
        this._setTitle(menus.length > 0 ? appDisplayName(model?.app_id) : '');
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

    _setTitle(name) {
        if (name) {
            this._title.text = name;
            this._title.visible = true;
        } else {
            this._title.visible = false;
        }
    }

    clear() {
        this._source = null;
        this._generation = 0;
        this._removeEntries();
        this._setTitle('');
        this._box.visible = false;
    }

    async populateMenu(menu, node) {
        const source = this._source;
        if (!source)
            return;
        const seq = menu._globalMenuSeq = (menu._globalMenuSeq ?? 0) + 1;
        menu.removeAll();
        menu.addMenuItem(loadingItem());

        source.opened(node.id);
        let children;
        try {
            ({children} = await source.getChildren(node.id));
        } catch (e) {
            console.warn(`GlobalMenu: fetching ${node.label} failed: ${e.message}`);
            children = [];
        }
        console.log(`GlobalMenu: populate '${node.label}': ${children?.length ?? 0} items (still open=${menu.isOpen})`);
        if (!menu.isOpen || menu._globalMenuSeq !== seq)
            return; // closed or repopulated while we were fetching
        menu.removeAll();
        this._buildItems(menu, children ?? []);
    }

    _buildItems(menu, nodes) {
        // Qt collapses leading/trailing/adjacent separators at render time;
        // dbusmenu exports them verbatim (VLC's Playback menu has three in a
        // row where context-dependent items sit hidden between them). The
        // shell only collapses separators present when the menu opens, and we
        // populate after that — so collapse them ourselves.
        nodes = nodes.filter((node, i, all) => {
            if (node.type !== 'separator')
                return true;
            const prev = all[i - 1];
            return prev !== undefined && prev.type !== 'separator';
        });
        while (nodes.at(-1)?.type === 'separator')
            nodes.pop();

        for (const node of nodes) {
            if (node.type === 'separator') {
                menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                continue;
            }
            if (node.type === 'submenu') {
                const sub = new PopupMenu.PopupSubMenuMenuItem(node.label);
                sub.setSensitive(node.enabled !== false);
                // Seed: PopupSubMenu.open() also refuses to expand when empty.
                sub.menu.addMenuItem(loadingItem());
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
                        // The expand animation eased towards the placeholder's
                        // height; snap to the real content height.
                        sub.menu.actor.remove_all_transitions();
                        sub.menu.actor.set_height(-1);
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
            menu.addMenuItem(loadingItem('(empty)'));
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
