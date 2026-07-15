// Menu search: fuzzy-find any menu item of the focused app and activate it.
//
// Opens as a popup anchored to the menu bar. On first use per menubar
// generation it crawls the menu tree through the same source interface the
// renderer uses (so it works identically for gmenu/dbusmenu/atspi), with a
// node/time budget so a huge or slow app yields partial results instead of a
// hang. The index is cached until the menubar changes.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const MAX_NODES = 500;
const MAX_DEPTH = 6;
const CRAWL_BUDGET_MS = 3000;
const MAX_RESULTS = 8;

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

// Simple subsequence fuzzy match; higher is better, -1 = no match.
function fuzzyScore(query, text) {
    const q = query.toLowerCase();
    const t = text.toLowerCase();
    let score = 0;
    let ti = 0;
    let lastMatch = -2;
    for (const ch of q) {
        const found = t.indexOf(ch, ti);
        if (found < 0)
            return -1;
        if (found === lastMatch + 1)
            score += 3; // consecutive
        else if (found === 0 || t[found - 1] === ' ')
            score += 2; // word start
        else
            score += 1;
        lastMatch = found;
        ti = found + 1;
    }
    return score - t.length * 0.01; // light bias towards short labels
}

export class MenuSearch {
    constructor(menubar) {
        this._menubar = menubar;
        this._index = null;
        this._indexKey = '';
        this._menu = null;
    }

    destroy() {
        this._closeMenu();
        this._index = null;
        this._menubar = null;
    }

    toggle() {
        if (this._menu?.isOpen) {
            this._closeMenu();
            return;
        }
        const bar = this._menubar;
        if (!bar?.source || bar.roots.length === 0)
            return;
        this._openMenu();
    }

    // -- UI -------------------------------------------------------------------

    _openMenu() {
        this._closeMenu();

        const anchor = this._menubar.anchorActor;
        this._menu = new PopupMenu.PopupMenu(anchor, 0.0, St.Side.TOP);
        this._menu.actor.hide();
        this._menu.actor.add_style_class_name('global-menu-search');
        Main.uiGroup.add_child(this._menu.actor);
        Main.panel.menuManager.addMenu(this._menu);

        this._entry = new St.Entry({
            style_class: 'global-menu-search-entry',
            hint_text: 'Search menus…',
            can_focus: true,
            x_expand: true,
        });
        const entryItem = new PopupMenu.PopupBaseMenuItem({
            reactive: false,
            can_focus: false,
        });
        entryItem.add_child(this._entry);
        this._menu.addMenuItem(entryItem);

        this._resultsSection = new PopupMenu.PopupMenuSection();
        this._menu.addMenuItem(this._resultsSection);

        this._entry.clutter_text.connect('text-changed', () => this._refilter());
        this._entry.clutter_text.connect('activate', () => this._activateFirst());
        this._entry.connect('key-press-event', (_a, event) => {
            if (event.get_key_symbol() === Clutter.KEY_Down) {
                this._resultsSection.firstMenuItem?.grab_key_focus();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this._menu.connect('open-state-changed', (_m, open) => {
            if (!open)
                GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                    this._closeMenu();
                    return GLib.SOURCE_REMOVE;
                });
        });

        this._menu.open(true);
        this._entry.grab_key_focus();
        this._buildIndex().then(() => this._refilter()).catch(e =>
            console.warn(`GlobalMenu: search index failed: ${e.message}`));
    }

    _closeMenu() {
        if (!this._menu)
            return;
        const menu = this._menu;
        this._menu = null;
        this._entry = null;
        this._resultsSection = null;
        Main.panel.menuManager.removeMenu(menu);
        menu.destroy();
    }

    _refilter() {
        if (!this._menu)
            return;
        this._resultsSection.removeAll();
        const query = this._entry.get_text().trim();
        if (!this._index) {
            this._addInfo('Indexing…');
            return;
        }

        let hits;
        if (query.length === 0) {
            hits = [];
        } else {
            hits = this._index
                .map(item => ({item, score: fuzzyScore(query, item.searchText)}))
                .filter(h => h.score >= 0)
                .sort((a, b) => b.score - a.score)
                .slice(0, MAX_RESULTS);
        }

        for (const {item} of hits) {
            const menuItem = new PopupMenu.PopupMenuItem(item.pathLabel);
            if (item.enabled === false)
                menuItem.setSensitive(false);
            const accel = formatAccel(item.accel);
            if (accel) {
                menuItem.label.x_expand = true;
                menuItem.add_child(new St.Label({
                    text: accel,
                    style_class: 'global-menu-accel',
                    y_align: Clutter.ActorAlign.CENTER,
                }));
            }
            menuItem.connect('activate', () => this._activate(item));
            this._resultsSection.addMenuItem(menuItem);
        }

        if (hits.length === 0 && query.length > 0)
            this._addInfo('No matches');
    }

    _addInfo(text) {
        this._resultsSection.addMenuItem(
            new PopupMenu.PopupMenuItem(text, {reactive: false, can_focus: false}));
    }

    _activateFirst() {
        const first = this._index && this._resultsSection?.firstMenuItem;
        if (first?.sensitive)
            first.activate(Clutter.get_current_event());
    }

    _activate(item) {
        const bar = this._menubar;
        this._closeMenu();
        bar?.source?.activate(bar.generation, item.id).catch(e =>
            console.warn(`GlobalMenu: search activate failed: ${e.message}`));
    }

    // -- index ------------------------------------------------------------------

    async _buildIndex() {
        const bar = this._menubar;
        const key = `${bar.source?.constructor?.name}:${bar.generation}`;
        if (this._index && this._indexKey === key)
            return;
        this._index = null;
        this._indexKey = key;

        const t0 = GLib.get_monotonic_time();
        const source = bar.source;
        const index = [];
        let visited = 0;
        // BFS: [{id, path}]
        const queue = bar.roots.map(node => ({id: node.id, path: [node.label]}));

        while (queue.length > 0 && visited < MAX_NODES) {
            if ((GLib.get_monotonic_time() - t0) / 1000 > CRAWL_BUDGET_MS)
                break;
            if (bar.source !== source || this._menubar !== bar)
                return; // menubar changed under us; drop this crawl
            const {id, path} = queue.shift();
            if (path.length > MAX_DEPTH)
                continue;
            visited++;
            let children;
            try {
                ({children} = await source.getChildren(id));
            } catch {
                continue;
            }
            for (const node of children ?? []) {
                if (node.type === 'separator' || !node.label)
                    continue;
                if (node.type === 'submenu') {
                    queue.push({id: node.id, path: [...path, node.label]});
                    continue;
                }
                index.push({
                    id: node.id,
                    pathLabel: [...path, node.label].join(' ▸ '),
                    searchText: node.label,
                    accel: node.accel,
                    enabled: node.enabled,
                });
            }
        }

        console.log(`GlobalMenu: search indexed ${index.length} items (${visited} menus)`);
        this._index = index;
    }
}
