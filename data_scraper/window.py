"""Main application window with provider cards and progress panel."""

import logging
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gio, Gdk

from data_scraper.providers.base import BaseProvider, DataType, ExportProgress
from data_scraper.providers.google import GoogleProvider
from data_scraper.providers.microsoft import MicrosoftProvider
from data_scraper.providers.apple import AppleProvider
from data_scraper.iso_builder import IsoBuilder
from data_scraper.widgets.provider_card import ProviderCard
from data_scraper.widgets.progress_panel import ProgressPanel
from data_scraper.widgets.iso_dialog import IsoDialog

log = logging.getLogger(__name__)

_CSS = """
.cloud-scraper-window {
    background: @window_bg_color;
}
.export-btn {
    padding: 12px 48px;
    font-size: 15px;
    font-weight: 600;
    border-radius: 12px;
}
.dest-row {
    border-radius: 12px;
    padding: 4px 0;
}
.section-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: @dim_label_color;
}
.flash-btn {
    padding: 10px 36px;
    font-size: 14px;
    font-weight: 600;
    border-radius: 12px;
}
"""


class DataScraperWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(
            default_width=720,
            default_height=780,
            title="Cloud Scraper",
            **kwargs,
        )

        self._dest_dir = Path.home() / "Downloads" / "cloud-export"
        self._exporting = False
        self._flashing = False

        # Providers
        self._providers: list[BaseProvider] = [
            GoogleProvider(),
            MicrosoftProvider(),
            AppleProvider(),
        ]
        self._cards: list[ProviderCard] = []

        self._load_css()
        self._build_ui()

    def _load_css(self):
        css = Gtk.CssProvider()
        css.load_from_string(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_ui(self):
        # Toast overlay wraps everything
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        toolbar_view = Adw.ToolbarView()
        self._toast_overlay.set_child(toolbar_view)

        # Header bar with icon + title
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label())
        toolbar_view.add_top_bar(header)

        # Scrollable content
        scroll = Gtk.ScrolledWindow(vexpand=True)
        toolbar_view.set_content(scroll)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_start=28,
            margin_end=28,
            margin_top=12,
            margin_bottom=32,
        )
        scroll.set_child(content)

        # -- App header: logo in corner + title + subtitle --
        app_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        app_header.set_valign(Gtk.Align.CENTER)
        content.append(app_header)

        icon_path = Path("/opt/openfactory/cloud-scraper/resources/icons/cloud-scraper.svg")
        if not icon_path.exists():
            icon_path = Path(__file__).parent.parent / "resources" / "icons" / "cloud-scraper.svg"
        if icon_path.exists():
            icon = Gtk.Image.new_from_file(str(icon_path))
            icon.set_pixel_size(48)
            app_header.append(icon)

        header_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_text.set_valign(Gtk.Align.CENTER)
        app_header.append(header_text)

        title_label = Gtk.Label(label="Cloud Scraper", xalign=0)
        title_label.add_css_class("title-3")
        header_text.append(title_label)

        subtitle_label = Gtk.Label(label="Export your data from cloud services", xalign=0)
        subtitle_label.add_css_class("dim-label")
        subtitle_label.add_css_class("caption")
        header_text.append(subtitle_label)

        # -- Providers section --
        providers_label = Gtk.Label(label="ACCOUNTS")
        providers_label.add_css_class("section-label")
        providers_label.set_xalign(0)
        providers_label.set_margin_top(0)
        content.append(providers_label)

        providers_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )
        content.append(providers_box)

        for provider in self._providers:
            card = ProviderCard(provider)
            card.connect("connect-clicked", self._on_provider_connect, provider, card)
            card.connect("disconnect-clicked", self._on_provider_disconnect, provider, card)
            self._cards.append(card)
            providers_box.append(card)

        # -- Export destination --
        dest_label = Gtk.Label(label="DESTINATION")
        dest_label.add_css_class("section-label")
        dest_label.set_xalign(0)
        content.append(dest_label)

        dest_group = Adw.PreferencesGroup()
        content.append(dest_group)

        dest_row = Adw.ActionRow(
            title="Save to",
            subtitle=str(self._dest_dir),
        )
        dest_row.add_css_class("dest-row")
        self._dest_subtitle = dest_row

        choose_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER)
        choose_btn.add_css_class("flat")
        choose_btn.connect("clicked", self._on_choose_folder)
        dest_row.add_suffix(choose_btn)
        dest_group.add(dest_row)

        # -- Progress panel (hidden until export starts) --
        self._progress = ProgressPanel()
        content.append(self._progress)

        # -- Export button --
        btn_box = Gtk.Box()
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(4)
        content.append(btn_box)

        self._export_btn = Gtk.Button(label="Start Export")
        self._export_btn.add_css_class("suggested-action")
        self._export_btn.add_css_class("pill")
        self._export_btn.add_css_class("export-btn")
        self._export_btn.connect("clicked", self._on_start_export)
        btn_box.append(self._export_btn)

        # -- Flash to ISO button --
        flash_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        flash_box.set_halign(Gtk.Align.CENTER)
        flash_box.set_margin_top(8)
        content.append(flash_box)

        self._flash_btn = Gtk.Button(label="Flash to ISO")
        self._flash_btn.add_css_class("pill")
        self._flash_btn.add_css_class("flash-btn")
        self._flash_btn.set_icon_name("media-optical-symbolic")
        self._flash_btn.connect("clicked", self._on_flash_to_iso)
        flash_box.append(self._flash_btn)

        flash_hint = Gtk.Label(label="Bake exported data into a bootable ISO")
        flash_hint.add_css_class("dim-label")
        flash_hint.add_css_class("caption")
        flash_box.append(flash_hint)

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
            try:
                success = provider.authenticate()
            except Exception as e:
                log.error("Auth thread error for %s: %s", provider.name, e)
                provider.last_error = str(e)
                success = False
            GLib.idle_add(self._on_auth_done, provider, card, success)

        threading.Thread(target=auth_thread, daemon=True).start()

    def _show_apple_auth_dialog(self, provider: AppleProvider, card: ProviderCard):
        """Show a dialog to collect Apple ID credentials."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Apple ID Sign In",
            body=(
                "Enter your Apple ID and an app-specific password.\n"
                "Generate one at appleid.apple.com → Sign-In and Security → App-Specific Passwords"
            ),
        )

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
            reason = getattr(provider, "last_error", None) or "Unknown error"
            toast = Adw.Toast(title=f"{provider.name}: {reason}")
            toast.set_timeout(5)
            self._toast_overlay.add_toast(toast)
        return False

    def _on_provider_disconnect(self, card_widget, provider: BaseProvider, card: ProviderCard):
        provider.disconnect()
        card.refresh()

    def _on_flash_to_iso(self, button):
        """Handle Flash to ISO button click."""
        if self._flashing or self._exporting:
            return

        # Check that export dir has files
        if not self._dest_dir.is_dir() or not any(self._dest_dir.iterdir()):
            self._toast_overlay.add_toast(
                Adw.Toast(title="Export some data first before flashing to ISO")
            )
            return

        builder = IsoBuilder(self._dest_dir, self._flash_progress_cb)
        env = builder.detect_live_environment()

        if env.is_live and env.mount_point:
            # Live CD mode — use the source medium, ask for output path
            self._start_flash_save_dialog(builder, env)
        else:
            # Not a live CD — show ISO picker dialog
            iso_dialog = IsoDialog(self)

            def on_iso_selected(path):
                if path:
                    self._start_flash_save_dialog(builder, env, source_iso=path)

            iso_dialog.present(on_iso_selected)

    def _start_flash_save_dialog(self, builder, env, source_iso=None):
        """Show a save dialog for the output ISO, then start the build."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Save ISO As")
        dialog.set_initial_name("cloud-export.iso")

        try:
            downloads = Gio.File.new_for_path(str(Path.home() / "Downloads"))
            dialog.set_initial_folder(downloads)
        except Exception:
            pass

        def on_save_response(d, result):
            try:
                gfile = d.save_finish(result)
                if gfile:
                    output_path = Path(gfile.get_path())
                    self._run_flash_build(builder, env, source_iso, output_path)
            except Exception:
                pass  # User cancelled

        dialog.save(self, None, on_save_response)

    def _run_flash_build(self, builder, env, source_iso, output_path):
        """Start the ISO build in a background thread."""
        self._flashing = True
        self._flash_btn.set_sensitive(False)
        self._flash_btn.set_label("Building ISO...")
        self._export_btn.set_sensitive(False)
        self._progress.show_progress()

        def build_thread():
            try:
                if source_iso:
                    # User-provided ISO
                    actual_source = source_iso
                else:
                    # Live CD — copy from medium
                    import tempfile
                    work = Path(tempfile.mkdtemp(prefix="cloud-iso-live-"))
                    actual_source = builder.copy_live_iso(env, work)

                builder.build_iso(actual_source, output_path)
                GLib.idle_add(self._on_flash_done, True, output_path, None)
            except Exception as e:
                log.error("Flash to ISO failed: %s", e)
                GLib.idle_add(self._on_flash_done, False, output_path, str(e))

        threading.Thread(target=build_thread, daemon=True).start()

    def _flash_progress_cb(self, fraction, message):
        """Progress callback for IsoBuilder — thread-safe."""
        self._progress.update(fraction, message)

    def _on_flash_done(self, success, output_path, error):
        """Called on main thread when ISO build completes."""
        self._flashing = False
        self._flash_btn.set_sensitive(True)
        self._flash_btn.set_label("Flash to ISO")
        self._export_btn.set_sensitive(True)

        if success:
            self._progress.finish(f"ISO created: {output_path}")
            self._toast_overlay.add_toast(
                Adw.Toast(title=f"ISO saved to {output_path.name}")
            )
        else:
            self._progress.finish(f"Failed: {error}")
            self._toast_overlay.add_toast(
                Adw.Toast(title=f"ISO build failed: {error}")
            )
        return False

    def _on_start_export(self, button):
        if self._exporting or self._flashing:
            return

        export_plan: list[tuple[BaseProvider, list[DataType]]] = []
        for card in self._cards:
            if card.provider.is_authenticated:
                types = card.get_selected_data_types()
                if types:
                    export_plan.append((card.provider, types))

        if not export_plan:
            self._toast_overlay.add_toast(
                Adw.Toast(title="Connect to a provider and select data types first")
            )
            return

        self._exporting = True
        self._export_btn.set_sensitive(False)
        self._export_btn.set_label("Exporting...")
        self._flash_btn.set_sensitive(False)
        self._progress.show_progress()

        total_types = sum(len(types) for _, types in export_plan)
        completed = [0]

        def progress_cb(p: ExportProgress):
            try:
                type_progress = p.current / p.total if p.total > 0 else 0
                overall = (completed[0] + type_progress) / total_types
                self._progress.update(overall, p.message)
            except Exception:
                pass

        def export_thread():
            all_results = {}
            try:
                self._dest_dir.mkdir(parents=True, exist_ok=True)
                for provider, data_types in export_plan:
                    for dt in data_types:
                        try:
                            results = provider.export_data([dt], self._dest_dir, progress_cb)
                            all_results.update(results)
                        except Exception as e:
                            log.error("Export failed for %s/%s: %s", provider.name, dt.value, e)
                        completed[0] += 1
            except Exception as e:
                log.error("Export thread crashed: %s", e)
            finally:
                GLib.idle_add(self._on_export_done, all_results)

        threading.Thread(target=export_thread, daemon=True).start()

    def _on_export_done(self, results: dict):
        self._exporting = False
        self._export_btn.set_sensitive(True)
        self._export_btn.set_label("Start Export")
        self._flash_btn.set_sensitive(True)
        count = len(results)
        self._progress.finish(f"Saved {count} data type(s) to {self._dest_dir}")
        self._toast_overlay.add_toast(
            Adw.Toast(title=f"Export complete — {count} data types saved")
        )
        return False
