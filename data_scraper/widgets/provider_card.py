"""Card widget for each cloud provider."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GObject

from data_scraper.providers.base import BaseProvider, DataType
from data_scraper.widgets.data_type_row import DataTypeRow


class ProviderCard(Gtk.Box):
    """A card displaying a provider's connection status and data type toggles."""

    __gsignals__ = {
        "connect-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "disconnect-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, provider: BaseProvider):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )

        self.provider = provider
        self._data_type_rows: dict[DataType, DataTypeRow] = {}

        # Main frame
        frame = Gtk.Frame()
        frame.add_css_class("card")
        self.append(frame)

        inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_start=16,
            margin_end=16,
            margin_top=12,
            margin_bottom=12,
        )
        frame.set_child(inner)

        # Header row: provider name + status + connect button
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        inner.append(header)

        # Provider name
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label=provider.name)
        name_label.add_css_class("title-3")
        title_box.append(name_label)

        if provider.experimental:
            exp_badge = Gtk.Label(label="experimental")
            exp_badge.add_css_class("dim-label")
            exp_badge.add_css_class("caption")
            title_box.append(exp_badge)

        header.append(title_box)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        # Status indicator
        self._status_label = Gtk.Label(label="Not connected")
        self._status_label.add_css_class("dim-label")
        header.append(self._status_label)

        # Connect/disconnect button
        self._connect_btn = Gtk.Button(label="Connect")
        self._connect_btn.add_css_class("suggested-action")
        self._connect_btn.connect("clicked", self._on_connect_clicked)
        header.append(self._connect_btn)

        # Data type checkboxes in a flow box
        self._types_box = Gtk.FlowBox()
        self._types_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._types_box.set_max_children_per_line(5)
        self._types_box.set_min_children_per_line(2)
        self._types_box.set_row_spacing(4)
        self._types_box.set_column_spacing(8)
        self._types_box.set_homogeneous(True)
        inner.append(self._types_box)

        for dt in provider.supported_data_types:
            row = DataTypeRow(dt, provider.name)
            self._data_type_rows[dt] = row
            self._types_box.insert(row, -1)

        self._update_ui()

    def _on_connect_clicked(self, button):
        if self.provider.is_authenticated:
            self.emit("disconnect-clicked")
        else:
            self.emit("connect-clicked")

    def _update_ui(self):
        if self.provider.is_authenticated:
            email = self.provider.user_email or "Connected"
            self._status_label.set_text(email)
            self._status_label.remove_css_class("dim-label")
            self._status_label.add_css_class("success")
            self._connect_btn.set_label("Disconnect")
            self._connect_btn.remove_css_class("suggested-action")
            self._connect_btn.add_css_class("destructive-action")
        else:
            self._status_label.set_text("Not connected")
            self._status_label.remove_css_class("success")
            self._status_label.add_css_class("dim-label")
            self._connect_btn.set_label("Connect")
            self._connect_btn.remove_css_class("destructive-action")
            self._connect_btn.add_css_class("suggested-action")

    def refresh(self):
        """Update the UI to reflect current provider state."""
        self._update_ui()

    def get_selected_data_types(self) -> list[DataType]:
        """Return list of checked data types."""
        return [dt for dt, row in self._data_type_rows.items() if row.active]
