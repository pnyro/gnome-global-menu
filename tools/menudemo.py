#!/usr/bin/env python3
"""Test fixture for the tier-1 (native GMenu) source.

A minimal GtkApplication that exports a menubar via set_menubar(): sections,
a nested submenu, a checkbox, radios, accelerators, and an unregistered
(disabled) action. Activations print to stdout so an integration test — or a
human — can confirm the panel menu drives the app.

By default the in-window fallback menubar is suppressed (as if the shell
claimed it); run with GLOBALMENU_DEMO_INWINDOW=1 to show it for comparison.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

MENU_XML = """
<interface>
  <menu id="menubar">
    <submenu>
      <attribute name="label">_File</attribute>
      <section>
        <item>
          <attribute name="label">_New</attribute>
          <attribute name="action">app.new</attribute>
        </item>
        <item>
          <attribute name="label">_Open…</attribute>
          <attribute name="action">app.open</attribute>
          <attribute name="accel">&lt;Control&gt;o</attribute>
        </item>
      </section>
      <section>
        <item>
          <attribute name="label">Not _Registered</attribute>
          <attribute name="action">app.missing</attribute>
        </item>
        <item>
          <attribute name="label">_Quit</attribute>
          <attribute name="action">app.quit</attribute>
          <attribute name="accel">&lt;Control&gt;q</attribute>
        </item>
      </section>
    </submenu>
    <submenu>
      <attribute name="label">_View</attribute>
      <section>
        <item>
          <attribute name="label">Word _Wrap</attribute>
          <attribute name="action">app.wrap</attribute>
        </item>
      </section>
      <section>
        <item>
          <attribute name="label">Small</attribute>
          <attribute name="action">app.size</attribute>
          <attribute name="target">small</attribute>
        </item>
        <item>
          <attribute name="label">Large</attribute>
          <attribute name="action">app.size</attribute>
          <attribute name="target">large</attribute>
        </item>
      </section>
      <section>
        <submenu>
          <attribute name="label">Advanced</attribute>
          <item>
            <attribute name="label">Deep Item</attribute>
            <attribute name="action">app.deep</attribute>
          </item>
        </submenu>
      </section>
    </submenu>
  </menu>
</interface>
"""


class Demo(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.gnome.GlobalMenu.Demo")

    def do_startup(self):
        Gtk.Application.do_startup(self)

        for name in ("new", "open", "quit", "deep"):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", self._on_activate)
            self.add_action(action)
        # NOTE: "missing" is deliberately never registered.

        wrap = Gio.SimpleAction.new_stateful("wrap", None, GLib.Variant("b", False))
        wrap.connect("change-state", self._on_change_state)
        self.add_action(wrap)

        size = Gio.SimpleAction.new_stateful(
            "size", GLib.VariantType("s"), GLib.Variant("s", "small")
        )
        size.connect("change-state", self._on_change_state)
        self.add_action(size)

        self.set_accels_for_action("app.new", ["<Control>n"])
        self.set_accels_for_action("app.open", ["<Control>o"])
        self.set_accels_for_action("app.quit", ["<Control>q"])

        builder = Gtk.Builder.new_from_string(MENU_XML, -1)
        self.set_menubar(builder.get_object("menubar"))

        if not os.environ.get("GLOBALMENU_DEMO_INWINDOW"):
            Gtk.Settings.get_default().set_property("gtk-shell-shows-menubar", True)

    def do_activate(self):
        win = Gtk.ApplicationWindow(application=self)
        win.set_title("GlobalMenu Demo")
        win.set_default_size(420, 180)
        win.add(Gtk.Label(label="Menu activations are printed to stdout."))
        win.show_all()

    def _on_activate(self, action, param):
        print(f"activated: {action.get_name()}", flush=True)
        if action.get_name() == "quit":
            self.quit()

    def _on_change_state(self, action, value):
        print(f"state: {action.get_name()} -> {value.print_(False)}", flush=True)
        action.set_state(value)


if __name__ == "__main__":
    Demo().run()
