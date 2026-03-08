"""Main application window with provider cards and progress panel."""

import logging
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gio

from data_scraper.providers.base import BaseProvider, DataType, ExportProgress
from data_scraper.providers.google import GoogleProvider
from data_scraper.providers.microsoft import MicrosoftProvider
from data_scraper.providers.apple import AppleProvider
from data_scraper.widgets.provider_card import ProviderCard
from data_scraper.widgets.progress_panel import ProgressPanel

log = logging.getLogger(__name__)


class DataScraperWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(
            default_width=600,
            default_height=720,
            title="Data Scraper",
            **kwargs,
        )

        self._dest_dir = Path.home() / "Downloads" / "export"
        self._exporting = False

        # Providers
        self._providers: list[BaseProvider] = [
            GoogleProvider(),
            MicrosoftProvider(),
            AppleProvider(),
        ]
        self._cards: list[ProviderCard] = []

        self._build_ui()

    def _build_ui(self):
        # Main layout
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header bar
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        # Scrollable content
        scroll = Gtk.ScrolledWindow(vexpand=True)
        toolbar_view.set_content(scroll)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_start=24,
            margin_end=24,
            margin_top=16,
            margin_bottom=24,
        )
        scroll.set_child(content)

        # Export destination row
        dest_group = Adw.PreferencesGroup(title="Export Destination")
        content.append(dest_group)

        dest_row = Adw.ActionRow(
            title="Save to",
            subtitle=str(self._dest_dir),
        )
        self._dest_subtitle = dest_row

        choose_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER)
        choose_btn.add_css_class("flat")
        choose_btn.connect("clicked", self._on_choose_folder)
        dest_row.add_suffix(choose_btn)
        dest_group.add(dest_row)

        # Provider cards
        providers_label = Gtk.Label(label="Cloud Providers", xalign=0)
        providers_label.add_css_class("title-2")
        providers_label.set_margin_top(8)
        content.append(providers_label)

        for provider in self._providers:
            card = ProviderCard(provider)
            card.connect("connect-clicked", self._on_provider_connect, provider, card)
            card.connect("disconnect-clicked", self._on_provider_disconnect, provider, card)
            self._cards.append(card)
            content.append(card)

        # Progress panel
        self._progress = ProgressPanel()
        content.append(self._progress)

        # Start export button
        self._export_btn = Gtk.Button(label="Start Export")
        self._export_btn.add_css_class("suggested-action")
        self._export_btn.add_css_class("pill")
        self._export_btn.set_halign(Gtk.Align.CENTER)
        self._export_btn.set_margin_top(8)
        self._export_btn.connect("clicked", self._on_start_export)
        content.append(self._export_btn)

    def _on_choose_folder(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose Export Folder")
        try:
            initial = Gio.File.new_for_path(str(self._dest_dir))
            dialog.set_initial_folder(initial)
        except Exception:
            pass
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self._dest_dir = Path(folder.get_path())
                self._dest_subtitle.set_subtitle(str(self._dest_dir))
        except Exception:
            pass

    def _on_provider_connect(self, card_widget, provider: BaseProvider, card: ProviderCard):
        """Handle provider authentication in a background thread."""
        if isinstance(provider, AppleProvider):
            self._show_apple_auth_dialog(provider, card)
            return

        card_widget.set_sensitive(False)

        def auth_thread():
            success = provider.authenticate()
            GLib.idle_add(self._on_auth_done, provider, card, success)

        threading.Thread(target=auth_thread, daemon=True).start()

    def _show_apple_auth_dialog(self, provider: AppleProvider, card: ProviderCard):
        """Show a dialog to collect Apple ID credentials."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Apple ID Sign In",
            body="Enter your Apple ID and an app-specific password.\nGenerate one at appleid.apple.com/account/manage",
        )

        # Add input fields
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(24)
        box.set_margin_end(24)

        email_entry = Gtk.Entry(placeholder_text="Apple ID (email)")
        box.append(email_entry)

        password_entry = Gtk.PasswordEntry()
        password_entry.set_placeholder_text("App-specific password")
        password_entry.set_show_peek_icon(True)
        box.append(password_entry)

        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("signin", "Sign In")
        dialog.set_response_appearance("signin", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "signin":
                apple_id = email_entry.get_text().strip()
                password = password_entry.get_text().strip()
                if apple_id and password:
                    def auth():
                        success = provider.set_credentials(apple_id, password)
                        GLib.idle_add(self._on_auth_done, provider, card, success)
                    threading.Thread(target=auth, daemon=True).start()

        dialog.connect("response", on_response)
        dialog.present()

    def _on_auth_done(self, provider: BaseProvider, card: ProviderCard, success: bool):
        card.refresh()
        card.set_sensitive(True)
        if not success:
            toast = Adw.Toast(title=f"Failed to connect to {provider.name}")
            toast.set_timeout(3)
            # Find toast overlay or create one
            self._show_toast(toast)
        return False

    def _on_provider_disconnect(self, card_widget, provider: BaseProvider, card: ProviderCard):
        provider.disconnect()
        card.refresh()

    def _show_toast(self, toast: Adw.Toast):
        """Show a toast notification. Wraps content in overlay if needed."""
        # Walk up to find or create a toast overlay
        content = self.get_content()
        if isinstance(content, Adw.ToastOverlay):
            content.add_toast(toast)
        else:
            overlay = Adw.ToastOverlay()
            overlay.set_child(content)
            self.set_content(overlay)
            overlay.add_toast(toast)

    def _on_start_export(self, button):
        if self._exporting:
            return

        # Gather selected data types per connected provider
        export_plan: list[tuple[BaseProvider, list[DataType]]] = []
        for card in self._cards:
            if card.provider.is_authenticated:
                types = card.get_selected_data_types()
                if types:
                    export_plan.append((card.provider, types))

        if not export_plan:
            self._show_toast(Adw.Toast(title="No providers connected or data types selected"))
            return

        self._exporting = True
        self._export_btn.set_sensitive(False)
        self._export_btn.set_label("Exporting...")
        self._progress.show_progress()

        # Count total export tasks for progress tracking
        total_types = sum(len(types) for _, types in export_plan)
        completed = [0]

        def progress_cb(p: ExportProgress):
            if p.total > 0:
                type_progress = p.current / p.total
            else:
                type_progress = 0
            overall = (completed[0] + type_progress) / total_types
            self._progress.update(overall, p.message)

        def export_thread():
            self._dest_dir.mkdir(parents=True, exist_ok=True)
            all_results = {}

            for provider, data_types in export_plan:
                for dt in data_types:
                    try:
                        results = provider.export_data([dt], self._dest_dir, progress_cb)
                        all_results.update(results)
                    except Exception as e:
                        log.error("Export failed for %s/%s: %s", provider.name, dt.value, e)
                    completed[0] += 1

            GLib.idle_add(self._on_export_done, all_results)

        threading.Thread(target=export_thread, daemon=True).start()

    def _on_export_done(self, results: dict):
        self._exporting = False
        self._export_btn.set_sensitive(True)
        self._export_btn.set_label("Start Export")
        count = len(results)
        self._progress.finish(f"Export complete — {count} data type(s) saved to {self._dest_dir}")
        self._show_toast(Adw.Toast(title=f"Export complete! {count} data types saved."))
        return False
