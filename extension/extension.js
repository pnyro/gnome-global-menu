//    Global Menu
//    GNOME Shell extension
//    macOS-style global menu bar

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';


// D-Bus interface XML for our Global Menu service
const GlobalMenuInterface = `
<node>
  <interface name="org.gnome.GlobalMenu">
    <method name="GetCurrentMenu">
      <arg type="s" direction="out" name="menu_json"/>
    </method>
    <method name="ActivateMenuItem">
      <arg type="i" direction="in" name="item_id"/>
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="ActivateMenuItemByPath">
      <arg type="as" direction="in" name="path"/>
      <arg type="b" direction="out" name="success"/>
    </method>
    <signal name="MenuChanged">
      <arg type="s" name="app_name"/>
      <arg type="b" name="has_menu"/>
    </signal>
  </interface>
</node>`;


const GlobalMenuIndicator = GObject.registerClass(
    class GlobalMenuIndicator extends St.BoxLayout {
        _init() {
            super._init({
                style_class: 'panel-button',
                x_expand: false,
                y_expand: false,
            });

            // D-Bus proxy
            this._proxy = null;
            this._menuChangedSignalId = null;

            // Current menu data
            this._currentMenuData = null;
            this._topLevelMenus = [];

            // Initialize D-Bus connection
            this._initDBus();
        }

        _initDBus() {
            const GlobalMenuProxy = Gio.DBusProxy.makeProxyWrapper(GlobalMenuInterface);

            try {
                this._proxy = new GlobalMenuProxy(
                    Gio.DBus.session,
                    'org.gnome.GlobalMenu',
                    '/org/gnome/GlobalMenu'
                );

                // Listen to MenuChanged signal
                this._menuChangedSignalId = this._proxy.connectSignal(
                    'MenuChanged',
                    this._onMenuChanged.bind(this)
                );

                log('Global Menu: Connected to D-Bus service');

                // Get initial menu
                this._refreshMenu();

            } catch (e) {
                logError(e, 'Global Menu: Failed to connect to D-Bus service');
            }
        }

        _onMenuChanged(proxy, sender, [appName, hasMenu]) {
            log(`Global Menu: MenuChanged - ${appName}, has_menu=${hasMenu}`);

            if (hasMenu) {
                this._refreshMenu();
            } else {
                this._clearMenu();
            }
        }

        _refreshMenu() {
            if (!this._proxy) {
                return;
            }

            try {
                this._proxy.GetCurrentMenuRemote((result, error) => {
                    if (error) {
                        logError(error, 'Global Menu: Failed to get menu');
                        return;
                    }

                    const [menuJson] = result;
                    this._updateMenu(menuJson);
                });
            } catch (e) {
                logError(e, 'Global Menu: Error calling GetCurrentMenu');
            }
        }

        _updateMenu(menuJson) {
            try {
                const menuData = JSON.parse(menuJson);

                // Store current menu data
                this._currentMenuData = menuData;

                // Clear existing menus
                this._clearMenu();

                // Build new menus
                if (menuData.menus && menuData.menus.length > 0) {
                    this._buildTopLevelMenus(menuData.menus);
                    this.show();
                } else {
                    this.hide();
                }

            } catch (e) {
                logError(e, 'Global Menu: Failed to parse menu JSON');
            }
        }

        _clearMenu() {
            // Remove and destroy all top-level menu buttons
            this._topLevelMenus.forEach(menuButton => {
                if (menuButton.menu) {
                    Main.panel.menuManager.removeMenu(menuButton.menu);
                }
                this.remove_child(menuButton);
                menuButton.destroy();
            });
            this._topLevelMenus = [];

            this.hide();
        }

        _buildTopLevelMenus(menus) {
            menus.forEach((menuData, index) => {
                // Create a PanelMenu.Button for each top-level menu
                const menuButton = new PanelMenu.Button(0.0, menuData.label, false);

                // Set button label
                const label = new St.Label({
                    text: menuData.label,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                menuButton.add_child(label);

                // Build submenu items in the button's menu
                if (menuData.children && menuData.children.length > 0) {
                    this._buildMenuItems(menuButton.menu, menuData.children);
                }

                // Add to panel menu manager so it handles open/close properly
                Main.panel.menuManager.addMenu(menuButton.menu);

                // Add to our container
                this.add_child(menuButton);

                // Store for cleanup
                this._topLevelMenus.push(menuButton);
            });
        }

        _buildMenuItems(parentMenu, items) {
            items.forEach(itemData => {
                if (itemData.type === 'separator') {
                    parentMenu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                } else if (itemData.type === 'menu') {
                    // Submenu
                    const submenu = new PopupMenu.PopupSubMenuMenuItem(itemData.label);

                    if (itemData.children && itemData.children.length > 0) {
                        this._buildMenuItems(submenu.menu, itemData.children);
                    }

                    parentMenu.addMenuItem(submenu);
                } else {
                    // Regular menu item
                    let menuItem;

                    if (itemData.type === 'checkmenuitem' || itemData.type === 'radiomenuitem') {
                        // TODO: Use PopupMenu.PopupSwitchMenuItem or custom implementation
                        // For now, treat as regular item with checkbox indicator
                        const label = itemData.checked ? `✓ ${itemData.label}` : `  ${itemData.label}`;
                        menuItem = new PopupMenu.PopupMenuItem(label);
                    } else {
                        menuItem = new PopupMenu.PopupMenuItem(itemData.label);
                    }

                    // Disable if not enabled
                    if (itemData.enabled === false) {
                        menuItem.setSensitive(false);
                    }

                    // Handle activation
                    if (itemData.activatable) {
                        menuItem.connect('activate', () => {
                            this._activateMenuItem(itemData.id);
                        });
                    }

                    parentMenu.addMenuItem(menuItem);
                }
            });
        }

        _activateMenuItem(itemId) {
            if (!this._proxy) {
                return;
            }

            log(`Global Menu: Activating menu item ID ${itemId}`);

            try {
                this._proxy.ActivateMenuItemRemote(itemId, (result, error) => {
                    if (error) {
                        logError(error, 'Global Menu: Failed to activate menu item');
                    } else {
                        const [success] = result;
                        log(`Global Menu: Activation ${success ? 'succeeded' : 'failed'}`);
                    }
                });
            } catch (e) {
                logError(e, 'Global Menu: Error calling ActivateMenuItem');
            }
        }

        destroy() {
            // Disconnect D-Bus signals
            if (this._proxy && this._menuChangedSignalId) {
                this._proxy.disconnectSignal(this._menuChangedSignalId);
                this._menuChangedSignalId = null;
            }

            // Clean up menu buttons
            this._clearMenu();

            this._proxy = null;

            super.destroy();
        }
    });


export default class GlobalMenuExtension extends Extension {
    enable() {
        log('Global Menu: Enabling extension');

        this._indicator = new GlobalMenuIndicator();

        // Add to panel on the left side (after Activities button)
        Main.panel.addToStatusArea('global-menu-indicator', this._indicator, 1, 'left');
    }

    disable() {
        log('Global Menu: Disabling extension');

        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
