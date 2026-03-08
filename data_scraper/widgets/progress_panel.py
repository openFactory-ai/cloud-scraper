"""Download progress/status panel widget."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, GLib


class ProgressPanel(Gtk.Box):
    """Panel showing export progress with a progress bar and status label."""

    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=8,
        )

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self.append(self._progress_bar)

        self._status_label = Gtk.Label(label="Ready")
        self._status_label.set_xalign(0)
        self._status_label.add_css_class("dim-label")
        self._status_label.set_wrap(True)
        self.append(self._status_label)

        self.set_visible(False)

    def show_progress(self):
        self.set_visible(True)
        self._progress_bar.set_fraction(0)
        self._status_label.set_text("Starting export...")

    def update(self, fraction: float, message: str):
        """Update progress from any thread — schedules on main loop."""
        GLib.idle_add(self._do_update, fraction, message)

    def _do_update(self, fraction: float, message: str):
        self._progress_bar.set_fraction(min(fraction, 1.0))
        self._progress_bar.set_text(f"{int(fraction * 100)}%")
        self._status_label.set_text(message)
        return False

    def finish(self, message: str = "Export complete"):
        GLib.idle_add(self._do_finish, message)

    def _do_finish(self, message: str):
        self._progress_bar.set_fraction(1.0)
        self._progress_bar.set_text("100%")
        self._status_label.set_text(message)
        return False

    def hide_progress(self):
        self.set_visible(False)
