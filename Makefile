# GNOME Global Menu — user-local install for both components.

UUID        := globalmenu@gnome-shell-extensions
DATADIR     := $(HOME)/.local/share
EXT_DIR     := $(DATADIR)/gnome-shell/extensions/$(UUID)
DAEMON_DIR  := $(DATADIR)/gnome-globalmenu
SYSTEMD_DIR := $(HOME)/.config/systemd/user
DBUS_DIR    := $(DATADIR)/dbus-1/services

.PHONY: install install-extension install-daemon uninstall restart-daemon check

install: install-extension install-daemon
	@echo ""
	@echo "Installed. Enable with:"
	@echo "  gnome-extensions enable $(UUID)"
	@echo "then log out and back in (Wayland reload requirement)."

install-extension:
	mkdir -p $(EXT_DIR)/sources $(EXT_DIR)/schemas
	install -m644 extension/extension.js extension/menubar.js extension/search.js \
	    extension/metadata.json extension/stylesheet.css $(EXT_DIR)/
	install -m644 extension/prefs.js $(EXT_DIR)/ 2>/dev/null || true
	install -m644 extension/sources/*.js $(EXT_DIR)/sources/
	install -m644 extension/schemas/*.gschema.xml $(EXT_DIR)/schemas/
	glib-compile-schemas $(EXT_DIR)/schemas/

install-daemon:
	mkdir -p $(DAEMON_DIR) $(SYSTEMD_DIR) $(DBUS_DIR)
	rm -rf $(DAEMON_DIR)/globalmenu
	cp -r daemon/globalmenu $(DAEMON_DIR)/
	install -m644 data/gnome-globalmenu.service $(SYSTEMD_DIR)/
	sed 's|@DATADIR@|$(DATADIR)|' data/org.gnome.GlobalMenu.service.in \
	    > $(DBUS_DIR)/org.gnome.GlobalMenu.service
	systemctl --user daemon-reload

restart-daemon:
	systemctl --user restart gnome-globalmenu.service || true

uninstall:
	rm -rf $(EXT_DIR) $(DAEMON_DIR)
	rm -f $(SYSTEMD_DIR)/gnome-globalmenu.service
	rm -f $(DBUS_DIR)/org.gnome.GlobalMenu.service
	systemctl --user daemon-reload

check:
	python3 -m py_compile daemon/globalmenu/*.py daemon/globalmenu/sources/*.py
	@echo "daemon: syntax OK"
