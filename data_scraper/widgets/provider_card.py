"""Card widget for each cloud provider — polished Adwaita style."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GObject, Gdk

from data_scraper.providers.base import BaseProvider, DataType
from data_scraper.widgets.data_type_row import DataTypeRow

_CARD_CSS = """
.provider-card {
    border-radius: 14px;
    padding: 0;
}
.provider-card-inner {
    padding: 16px 18px;
}
.provider-name {
    font-size: 16px;
    font-weight: 700;
}
.provider-status {
    font-size: 12px;
}
.provider-status-connected {
    color: @success_color;
    font-weight: 600;
}
.connect-btn {
    border-radius: 8px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 13px;
}
.data-type-check {
    font-size: 13px;
}
"""

_css_loaded = False


def _ensure_css():
    global _css_loaded
    if _css_loaded:
        return
    css = Gtk.CssProvider()
    css.load_from_string(_CARD_CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _css_loaded = True


# Provider icon names — symbolic icons from the Adwaita icon theme
PROVIDER_ICONS = {
    "Google": "web-browser-symbolic",
    "Microsoft": "computer-symbolic",
    "Apple": "phone-symbolic",
}


class ProviderCard(Gtk.Box):
    """A card displaying a provider's connection status and data type toggles."""

    __gsignals__ = {
        "connect-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "disconnect-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, provider: BaseProvider):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        _ensure_css()

        self.provider = provider
        self._data_type_rows: dict[DataType, DataTypeRow] = {}

        # Card frame
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.add_css_class("provider-card")
        self.append(frame)

        inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
        )
        inner.add_css_class("provider-card-inner")
        frame.set_child(inner)

        # -- Header: icon + name/status + button --
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        header.set_valign(Gtk.Align.CENTER)
        inner.append(header)

        # Provider icon
        icon_name = PROVIDER_ICONS.get(provider.name, "cloud-symbolic")
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(28)
        icon.set_opacity(0.7)
        header.append(icon)

        # Name + status stacked
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        header.append(info)

        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        info.append(name_box)

        name_label = Gtk.Label(label=provider.name, xalign=0)
        name_label.add_css_class("provider-name")
        name_box.append(name_label)

        if provider.experimental:
            badge = Gtk.Label(label="beta")
            badge.add_css_class("dim-label")
            badge.add_css_class("caption")
            badge.set_valign(Gtk.Align.CENTER)
            name_box.append(badge)

        self._status_label = Gtk.Label(xalign=0)
        self._status_label.add_css_class("provider-status")
        info.append(self._status_label)

        # Connect / Disconnect button
        self._connect_btn = Gtk.Button()
        self._connect_btn.add_css_class("connect-btn")
        self._connect_btn.set_valign(Gtk.Align.CENTER)
        self._connect_btn.connect("clicked", self._on_connect_clicked)
        header.append(self._connect_btn)

        # -- Data type toggles --
        self._types_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=16,
        )
        self._types_box.set_margin_top(2)
        self._types_box.set_margin_start(42)  # align with text after icon
        inner.append(self._types_box)

        for dt in provider.supported_data_types:
            row = DataTypeRow(dt, provider.name)
            row.add_css_class("data-type-check")
            self._data_type_rows[dt] = row
            self._types_box.append(row)

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
            self._status_label.add_css_class("provider-status-connected")
            self._connect_btn.set_label("Disconnect")
            self._connect_btn.remove_css_class("suggested-action")
            self._connect_btn.add_css_class("destructive-action")
            self._types_box.set_sensitive(True)
        else:
            self._status_label.set_text("Not connected")
            self._status_label.add_css_class("dim-label")
            self._status_label.remove_css_class("provider-status-connected")
            self._connect_btn.set_label("Connect")
            self._connect_btn.remove_css_class("destructive-action")
            self._connect_btn.add_css_class("suggested-action")
            self._types_box.set_sensitive(False)

    def refresh(self):
        self._update_ui()

    def get_selected_data_types(self) -> list[DataType]:
        return [dt for dt, row in self._data_type_rows.items() if row.active]
