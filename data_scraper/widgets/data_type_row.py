"""Toggleable row widget for each data type."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, GObject

from data_scraper.providers.base import DataType


# Display labels for data types
DATA_TYPE_LABELS = {
    DataType.EMAIL: "Email",
    DataType.CONTACTS: "Contacts",
    DataType.CALENDAR: "Calendar",
    DataType.DRIVE: "Drive",
    DataType.PHOTOS: "Photos",
}

# Per-provider label overrides
PROVIDER_LABELS = {
    "Microsoft": {DataType.DRIVE: "OneDrive"},
    "Apple": {DataType.DRIVE: "iCloud Drive"},
}


class DataTypeRow(Gtk.Box):
    """A check button for a single data type."""

    __gsignals__ = {
        "toggled": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, data_type: DataType, provider_name: str = ""):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.data_type = data_type

        # Get label with provider-specific override
        overrides = PROVIDER_LABELS.get(provider_name, {})
        label = overrides.get(data_type, DATA_TYPE_LABELS.get(data_type, data_type.value))

        self._check = Gtk.CheckButton(label=label, active=True)
        self._check.connect("toggled", self._on_toggled)
        self.append(self._check)

    @property
    def active(self) -> bool:
        return self._check.get_active()

    @active.setter
    def active(self, value: bool):
        self._check.set_active(value)

    def _on_toggled(self, button):
        self.emit("toggled", button.get_active())
