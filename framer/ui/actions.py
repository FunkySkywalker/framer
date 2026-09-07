"""Window action group, GMenu model, hamburger button, accelerators."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, Gtk

ACTION_NAMES = (
    "add-files",
    "add-folder",
    "start",
    "cancel",
    "clear",
    "clear-finished",
    "about",
    "settings",
    "close",
)

ACCELERATORS = {
    "win.add-files": ["<Primary>o"],
    "win.add-folder": ["<Primary><Shift>o"],
    "win.start": ["<Primary>Return"],
    "win.cancel": ["<Primary>period"],
    "win.close": ["<Primary>w"],
}


class Actions:
    """Builds the ``win`` action group and wires menu + accelerators."""

    def __init__(self) -> None:
        self.group = Gio.SimpleActionGroup()
        self._actions: dict[str, Gio.SimpleAction] = {}
        for name in ACTION_NAMES:
            action = Gio.SimpleAction.new(name, None)
            self._actions[name] = action
            self.group.add_action(action)
        self._actions["start"].set_enabled(False)
        self._actions["cancel"].set_enabled(False)

    def install(self, window, callbacks: dict) -> Gtk.MenuButton:
        """Install the group on ``window``, wire callbacks, build the menu.

        Returns the hamburger ``Gtk.MenuButton`` to pack into the header.
        """
        window.insert_action_group("win", self.group)
        for name, cb in callbacks.items():
            action = self.group.lookup_action(name)
            action.connect("activate", lambda _a, _p, cb=cb: cb())

        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Clear finished", "win.clear-finished")
        section.append("Clear all", "win.clear")
        section.append("Settings…", "win.settings")
        section.append("About Framer", "win.about")
        menu.append_section(None, section)
        menu.append("Quit", "app.quit")

        button = Gtk.MenuButton.new()
        button.set_icon_name("open-menu-symbolic")
        button.set_menu_model(menu)

        app = window.get_application()
        if app is not None:
            for action, accels in ACCELERATORS.items():
                app.set_accels_for_action(action, accels)
        return button

    # -- sensitivity ------------------------------------------------------

    def set_start_enabled(self, enabled: bool) -> None:
        self._actions["start"].set_enabled(enabled)

    def set_cancel_enabled(self, enabled: bool) -> None:
        self._actions["cancel"].set_enabled(enabled)

    def set_clear_enabled(self, enabled: bool) -> None:
        self._actions["clear"].set_enabled(enabled)
        self._actions["clear-finished"].set_enabled(enabled)
