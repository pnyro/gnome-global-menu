import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

// 1. D-Bus Interface Definition
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
    <signal name="MenuChanged">
      <arg type="s" name="app_name"/>
      <arg type="b" name="has_menu"/>
    </signal>
  </interface>
</node>`;

// 2. The Menu Button Class (Represents "File", "Edit", etc.)
const GlobalMenuItem = GObject.registerClass(
    class GlobalMenuItem extends PanelMenu.Button {
        _init(label, children, dbusProxy) {
            // Standard Init: 0.0 alignment, name
            super._init(0.0, `GlobalMenu-${label}`);

            this._dbusProxy = dbusProxy;

            // Visual Label
            const labelActor = new St.Label({
                text: label,
                y_align: Clutter.ActorAlign.CENTER,
                style_class: 'panel-button-text'
            });
            this.add_child(labelActor);

            // Safety: Ensure menu exists (AppIndicator pattern)
            if (!this.menu) {
                this.menu = new PopupMenu.PopupMenu(this, 0.0, St.Side.BOTTOM);
                this.setMenu(this.menu);
            }

            // Recursively build the menu structure
            if (children && children.length > 0) {
                this._buildMenu(this.menu, children);
            }
        }

        _buildMenu(parentMenu, items) {
            items.forEach(item => {
                if (item.type === 'separator') {
                    parentMenu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                } else if (item.type === 'menu') {
                    // Submenu
                    const submenu = new PopupMenu.PopupSubMenuMenuItem(item.label);
                    // Recursion for nested menus
                    if (item.children) {
                        this._buildMenu(submenu.menu, item.children);
                    }
                    parentMenu.addMenuItem(submenu);
                } else {
                    // Standard Menu Item
                    const menuItem = new PopupMenu.PopupMenuItem(item.label);
                    
                    // Handle enabled/disabled state
                    if (item.enabled === false) {
                        menuItem.setSensitive(false);
                    }

                    // Handle Checkboxes / Radio buttons (visual only for now)
                    if (item.checked) {
                        menuItem.setOrnament(PopupMenu.Ornament.CHECK);
                    }

                    // Connect Click Event -> D-Bus Activation
                    if (item.activatable !== false) {
                        menuItem.connect('activate', () => {
                            this._activate(item.id);
                        });
                    }
                    parentMenu.addMenuItem(menuItem);
                }
            });
        }

        _activate(itemId) {
            if (this._dbusProxy) {
                log(`GlobalMenu: Activating Item ID ${itemId}`);
                this._dbusProxy.ActivateMenuItemRemote(itemId, (result, error) => {
                    if (error) {
                        logError(error, `GlobalMenu: Activation failed for ID ${itemId}`);
                    }
                });
            }
        }
    }
);

// 3. The Main Extension Class
export default class GlobalMenuExtension extends Extension {
    enable() {
        log('Global Menu: Enabling...');
        
        this._items = []; // Store our active buttons
        
        // Initialize D-Bus connection
        this._initDBus();
    }

    _initDBus() {
        const GlobalMenuProxy = Gio.DBusProxy.makeProxyWrapper(GlobalMenuInterface);
        
        try {
            this._proxy = new GlobalMenuProxy(
                Gio.DBus.session,
                'org.gnome.GlobalMenu',
                '/org/gnome/GlobalMenu',
                (proxy, error) => {
                    if (error) {
                        logError(error, 'Global Menu: Failed to connect to DBus Proxy');
                        return;
                    }
                    
                    // Connected! Listen for changes.
                    this._proxy.connectSignal('MenuChanged', this._onMenuChanged.bind(this));
                    
                    // Get the initial state immediately
                    this._fetchMenu();
                }
            );
        } catch (e) {
            logError(e, 'Global Menu: DBus Init Error');
        }
    }

    _onMenuChanged(proxy, sender, [appName, hasMenu]) {
        log(`Global Menu: Signal received for ${appName} (has_menu: ${hasMenu})`);
        if (hasMenu) {
            this._fetchMenu();
        } else {
            this._destroyMenu();
        }
    }

    _fetchMenu() {
        this._proxy.GetCurrentMenuRemote((result, error) => {
            if (error) {
                logError(error, 'Global Menu: Failed to get menu data');
                return;
            }
            
            // Result is a tuple [jsonString], unwrapped by generated proxy
            // But makeProxyWrapper usually returns [result] in callback
            const jsonString = Array.isArray(result) ? result[0] : result;
            this._updateUI(jsonString);
        });
    }

    _updateUI(jsonString) {
        try {
            const data = JSON.parse(jsonString);
            
            // 1. Cleanup existing items
            this._destroyMenu();

            // 2. Verify data
            if (!data.menus || data.menus.length === 0) {
                return;
            }

            // 3. Create new items
            data.menus.forEach((menuData, index) => {
                const item = new GlobalMenuItem(menuData.label, menuData.children, this._proxy);
                
                // Unique ID for addToStatusArea
                const id = `global-menu-item-${index}`;
                
                // Insert into panel (after Activities)
                // We use index + 1 to stack them in order from left to right
                Main.panel.addToStatusArea(id, item, index + 1, 'left');
                
                this._items.push(item);
            });
            
            log(`Global Menu: Rendered ${this._items.length} top-level items`);

        } catch (e) {
            logError(e, 'Global Menu: JSON Parsing Error');
        }
    }

    _destroyMenu() {
        if (this._items) {
            this._items.forEach(item => item.destroy());
        }
        this._items = [];
    }

    disable() {
        log('Global Menu: Disabling...');
        this._destroyMenu();
        this._proxy = null;
    }
}
