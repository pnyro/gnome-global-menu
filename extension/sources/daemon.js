// D-Bus client for the helper daemon (tiers 2/3/4).
// All calls are async; the compositor thread never blocks on the daemon.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const BUS_NAME = 'org.gnome.GlobalMenu';
const OBJECT_PATH = '/org/gnome/GlobalMenu';

const IFACE_XML = `
<node>
  <interface name="org.gnome.GlobalMenu">
    <property name="Version" type="u" access="read"/>
    <method name="SetActiveWindow">
      <arg type="a{sv}" name="info" direction="in"/>
    </method>
    <method name="GetMenuBar">
      <arg type="s" name="menubar_json" direction="out"/>
    </method>
    <method name="GetChildren">
      <arg type="s" name="node_id" direction="in"/>
      <arg type="s" name="children_json" direction="out"/>
    </method>
    <method name="Activate">
      <arg type="u" name="generation" direction="in"/>
      <arg type="s" name="node_id" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="Opened">
      <arg type="s" name="node_id" direction="in"/>
    </method>
    <method name="Closed">
      <arg type="s" name="node_id" direction="in"/>
    </method>
    <signal name="MenuBarChanged">
      <arg type="u" name="generation"/>
    </signal>
    <signal name="MenuUpdated">
      <arg type="u" name="generation"/>
      <arg type="s" name="node_id"/>
    </signal>
  </interface>
</node>`;

const EMPTY_BAR = {source: '', generation: 0, app_id: '', menus: []};

export class DaemonClient {
    constructor({onMenuBarChanged, onMenuUpdated, onOwnerChanged} = {}) {
        this._signalIds = [];
        this._ready = false;

        const Wrapper = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);
        this._proxy = new Wrapper(
            Gio.DBus.session,
            BUS_NAME,
            OBJECT_PATH,
            (proxy, error) => {
                if (error) {
                    console.warn(`GlobalMenu: daemon proxy init failed: ${error.message}`);
                    return;
                }
                this._ready = true;
                onOwnerChanged?.(this.hasOwner);
            });

        if (onMenuBarChanged)
            this._signalIds.push(this._proxy.connectSignal('MenuBarChanged',
                (_p, _s, [generation]) => onMenuBarChanged(generation)));
        if (onMenuUpdated)
            this._signalIds.push(this._proxy.connectSignal('MenuUpdated',
                (_p, _s, [generation, nodeId]) => onMenuUpdated(generation, nodeId)));

        this._ownerId = this._proxy.connect('notify::g-name-owner',
            () => onOwnerChanged?.(this.hasOwner));
    }

    get hasOwner() {
        return !!this._proxy?.g_name_owner;
    }

    _call(method, ...args) {
        return new Promise((resolve, reject) => {
            if (!this._proxy)
                return reject(new Error('daemon client destroyed'));
            this._proxy[`${method}Remote`](...args, (result, error) => {
                if (error)
                    reject(error);
                else
                    resolve(result);
            });
        });
    }

    async setActiveWindow({pid = 0, appId = '', title = '', xid = 0} = {}) {
        const info = {
            pid: GLib.Variant.new_int32(pid),
            app_id: GLib.Variant.new_string(appId),
            title: GLib.Variant.new_string(title),
            xid: GLib.Variant.new_int32(xid),
        };
        await this._call('SetActiveWindow', info);
    }

    async getMenuBar() {
        try {
            const [json] = await this._call('GetMenuBar');
            return JSON.parse(json);
        } catch (e) {
            console.warn(`GlobalMenu: GetMenuBar failed: ${e.message}`);
            return EMPTY_BAR;
        }
    }

    async getChildren(nodeId) {
        const [json] = await this._call('GetChildren', nodeId);
        return JSON.parse(json);
    }

    async activate(generation, nodeId) {
        const [ok] = await this._call('Activate', generation, nodeId);
        if (!ok)
            console.warn(`GlobalMenu: activation refused for ${nodeId} (gen ${generation})`);
        return ok;
    }

    opened(nodeId) {
        this._call('Opened', nodeId).catch(() => {});
    }

    closed(nodeId) {
        this._call('Closed', nodeId).catch(() => {});
    }

    destroy() {
        for (const id of this._signalIds)
            this._proxy.disconnectSignal(id);
        this._signalIds = [];
        if (this._ownerId) {
            this._proxy.disconnect(this._ownerId);
            this._ownerId = 0;
        }
        this._proxy = null;
    }
}
