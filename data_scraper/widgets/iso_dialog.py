"""ISO file picker dialog for non-live-CD environments."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from pathlib import Path

from gi.repository import Gtk, Adw, Gio


class IsoDialog:
    """Dialog for selecting an ISO file to use as the base image.

    Presents options for picking a local ISO file (functional) and
    future download options (greyed out).

    Usage:
        dialog = IsoDialog(parent_window)
        dialog.present(callback)
        # callback(path: Path | None) called when dialog closes
    """

    def __init__(self, parent: Adw.ApplicationWindow):
        self._parent = parent
        self._callback = None
        self._selected_path: Path | None = None

    def present(self, callback):
        """Show the dialog.

        Args:
            callback: Called with Path to selected ISO, or None if cancelled.
        """
        self._callback = callback
        self._selected_path = None

        dialog = Adw.MessageDialog(
            transient_for=self._parent,
            heading="Select Base ISO",
            body="Choose an ISO image to bake your exported data into.",
        )

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_start(12)
        content.set_margin_end(12)

        # Option: Browse for local file
        browse_row = Adw.ActionRow(
            title="Browse for a local ISO file...",
            subtitle="Select an Ubuntu or Fedora live ISO from your computer",
        )
        browse_row.set_activatable(True)
        browse_icon = Gtk.Image(icon_name="folder-open-symbolic")
        browse_row.add_suffix(browse_icon)

        browse_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        browse_list.add_css_class("boxed-list")
        browse_list.append(browse_row)
        content.append(browse_list)

        # Status label — shows selected file
        self._status_label = Gtk.Label(label="")
        self._status_label.set_xalign(0)
        self._status_label.add_css_class("dim-label")
        self._status_label.add_css_class("caption")
        self._status_label.set_margin_top(4)
        self._status_label.set_visible(False)
        content.append(self._status_label)

        # Future options (greyed out)
        future_label = Gtk.Label(label="COMING SOON")
        future_label.add_css_class("dim-label")
        future_label.add_css_class("caption")
        future_label.set_xalign(0)
        future_label.set_margin_top(12)
        content.append(future_label)

        future_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        future_list.add_css_class("boxed-list")
        future_list.set_sensitive(False)

        ubuntu_row = Adw.ActionRow(
            title="Ubuntu 24.04 LTS",
            subtitle="Download from official mirror",
        )
        ubuntu_icon = Gtk.Image(icon_name="emblem-system-symbolic")
        ubuntu_row.add_suffix(ubuntu_icon)
        future_list.append(ubuntu_row)

        fedora_row = Adw.ActionRow(
            title="Fedora Workstation 41",
            subtitle="Download from official mirror",
        )
        fedora_icon = Gtk.Image(icon_name="emblem-system-symbolic")
        fedora_row.add_suffix(fedora_icon)
        future_list.append(fedora_row)

        content.append(future_list)

        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("select", "Build ISO")
        dialog.set_response_appearance("select", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_enabled("select", False)

        # Wire up browse action
        self._dialog = dialog
        browse_row.connect("activated", self._on_browse_clicked)
        dialog.connect("response", self._on_response)
        dialog.present()

    def _on_browse_clicked(self, row):
        """Open a file dialog to pick an ISO."""
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title("Select ISO Image")

        # Filter for ISO files
        iso_filter = Gtk.FileFilter()
        iso_filter.set_name("ISO Images")
        iso_filter.add_pattern("*.iso")
        iso_filter.add_mime_type("application/x-iso9660-image")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(iso_filter)
        file_dialog.set_filters(filters)
        file_dialog.set_default_filter(iso_filter)

        # Start in Downloads
        try:
            downloads = Gio.File.new_for_path(
                str(Path.home() / "Downloads")
            )
            file_dialog.set_initial_folder(downloads)
        except Exception:
            pass

        file_dialog.open(self._parent, None, self._on_file_selected)

    def _on_file_selected(self, dialog, result):
        """Handle file selection result."""
        try:
            gfile = dialog.open_finish(result)
            if gfile:
                path = Path(gfile.get_path())
                self._selected_path = path
                self._status_label.set_text(f"Selected: {path.name}")
                self._status_label.set_visible(True)
                self._dialog.set_response_enabled("select", True)
        except Exception:
            # User cancelled the file dialog
            pass

    def _on_response(self, dialog, response):
        """Handle dialog response."""
        if response == "select" and self._selected_path:
            self._callback(self._selected_path)
        else:
            self._callback(None)
