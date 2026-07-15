//    Global Menu - Preferences
//    GNOME Shell extension

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';


export default class GlobalMenuPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage({
            title: 'General',
            icon_name: 'open-menu-symbolic',
        });
        window.add(page);

        const behavior = new Adw.PreferencesGroup({
            title: 'Menu Bar',
        });
        page.add(behavior);

        const accelsRow = new Adw.SwitchRow({
            title: 'Show keyboard shortcuts',
            subtitle: 'Display accelerator hints next to menu items',
        });
        behavior.add(accelsRow);
        settings.bind('show-accels', accelsRow, 'active',
            Gio.SettingsBindFlags.DEFAULT);

        const keys = new Adw.PreferencesGroup({
            title: 'Keyboard Shortcuts',
            description: 'Edit with dconf under /org/gnome/shell/extensions/globalmenu/',
        });
        page.add(keys);

        keys.add(new Adw.ActionRow({
            title: 'Search menus',
            subtitle: settings.get_strv('menu-search').join(', ') || 'unset',
        }));
        keys.add(new Adw.ActionRow({
            title: 'Open first menu',
            subtitle: settings.get_strv('open-first-menu').join(', ') || 'unset',
        }));

        const about = new Adw.PreferencesGroup({
            title: 'How it works',
            description: 'Menus come from the best available source per app: ' +
                'native GMenu (in-process), the AppMenu registrar (Qt), or ' +
                'AT-SPI scraping via the helper daemon ' +
                '(gnome-globalmenu.service, started on demand).',
        });
        page.add(about);
    }
}
