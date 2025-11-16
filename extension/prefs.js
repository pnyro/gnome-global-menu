//    Global Menu - Preferences
//    GNOME Shell extension

import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';

import { ExtensionPreferences } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';


export default class GlobalMenuPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        // Create a preferences page
        const page = new Adw.PreferencesPage({
            title: 'General',
            icon_name: 'dialog-information-symbolic',
        });
        window.add(page);

        // Create a preferences group
        const group = new Adw.PreferencesGroup({
            title: 'Global Menu Settings',
            description: 'Configure the global menu bar behavior',
        });
        page.add(group);

        // Info row
        const infoRow = new Adw.ActionRow({
            title: 'Global Menu',
            subtitle: 'macOS-style menu bar for GNOME',
        });
        group.add(infoRow);

        // Instructions
        const instructions = new Adw.PreferencesGroup({
            title: 'Requirements',
            description: 'The Global Menu extension requires the helper daemon to be running',
        });
        page.add(instructions);

        const daemonRow = new Adw.ActionRow({
            title: 'Helper Daemon',
            subtitle: 'Run: python3 globalmenu_service.py',
        });
        instructions.add(daemonRow);

        // TODO: Add more preferences in the future
        // - Blacklist apps
        // - Show/hide app name
        // - Keyboard shortcuts
    }
}
