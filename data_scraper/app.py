"""Adw.Application subclass for Data Scraper."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio

from data_scraper import APP_ID
from data_scraper.window import DataScraperWindow


class DataScraperApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = DataScraperWindow(application=self)
        win.present()
