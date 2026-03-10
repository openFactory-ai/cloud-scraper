"""Microsoft data export provider — Outlook Mail, Contacts, Calendar, OneDrive."""

import json
import logging
from pathlib import Path

from data_scraper.providers.base import BaseProvider, DataType, ExportProgress, ProgressCallback
from data_scraper.utils.storage import store_token, load_token, delete_token

log = logging.getLogger(__name__)

SCOPES = ["Mail.Read", "Contacts.Read", "Calendars.Read", "Files.Read", "User.Read"]
REDIRECT_PORT = 8086
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

# Embedded Azure AD app registration — public client (no secret needed for
# desktop/mobile apps using device code flow)
_EMBEDDED_CLIENT_ID = ""


class MicrosoftProvider(BaseProvider):
    name = "Microsoft"
    icon_name = "microsoft"
    supported_data_types = [
        DataType.EMAIL,
        DataType.CONTACTS,
        DataType.CALENDAR,
        DataType.DRIVE,
    ]

    def __init__(self):
        super().__init__()
        self._access_token: str | None = None
        self._client_id = self._load_client_id()

    def _load_client_id(self) -> str:
        """Load client ID — file override, or embedded default."""
        config_path = Path.home() / ".config" / "data-scraper" / "microsoft.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
                cid = data.get("client_id", "")
                if cid:
                    return cid
            except Exception as e:
                log.warning("Failed to load %s: %s", config_path, e)
        return _EMBEDDED_CLIENT_ID

    def authenticate(self) -> bool:
        self.last_error = None
        try:
            import msal
        except ImportError:
            self.last_error = "msal not installed"
            log.error(self.last_error)
            return False

        if not self._client_id:
            self.last_error = "No Microsoft client ID configured"
            log.error(self.last_error)
            return False

        # Try cached token
        token_data = load_token("microsoft")
        if token_data and "access_token" in token_data:
            self._access_token = token_data["access_token"]
            # Validate token
            if self._fetch_user_info():
                self._authenticated = True
                return True

        # Interactive flow
        app = msal.PublicClientApplication(
            self._client_id,
            authority="https://login.microsoftonline.com/common",
        )

        flow = app.initiate_device_flow(scopes=[f"https://graph.microsoft.com/{s}" for s in SCOPES])
        if "user_code" not in flow:
            self.last_error = f"Device flow failed: {flow.get('error_description', 'unknown')}"
            log.error(self.last_error)
            return False

        log.info("Microsoft auth: %s", flow["message"])
        # Open browser with the verification URL
        import webbrowser
        webbrowser.open(flow["verification_uri"])

        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            self.last_error = f"Auth failed: {result.get('error_description', 'unknown')}"
            log.error(self.last_error)
            return False

        self._access_token = result["access_token"]
        store_token("microsoft", {
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token", ""),
        })

        self._fetch_user_info()
        self._authenticated = True
        return True

    def _fetch_user_info(self) -> bool:
        import requests
        try:
            r = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=self._auth_headers(),
                timeout=10,
            )
            if r.status_code == 200:
                self._user_email = r.json().get("mail") or r.json().get("userPrincipalName")
                return True
        except Exception as e:
            log.warning("Failed to fetch user info: %s", e)
        return False

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    def export_data(
        self,
        data_types: list[DataType],
        dest_dir: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> dict[DataType, Path]:
        results = {}
        exporters = {
            DataType.EMAIL: self._export_email,
            DataType.CONTACTS: self._export_contacts,
            DataType.CALENDAR: self._export_calendar,
            DataType.DRIVE: self._export_drive,
        }
        for dt in data_types:
            if dt in exporters:
                try:
                    path = exporters[dt](dest_dir, progress_cb)
                    if path:
                        results[dt] = path
                except Exception as e:
                    log.error("Failed to export %s: %s", dt.value, e)
                    if progress_cb:
                        progress_cb(ExportProgress(dt, 0, 0, f"Error: {e}"))
        return results

    def _graph_get(self, url: str, params: dict | None = None) -> dict:
        import requests
        r = requests.get(url, headers=self._auth_headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _graph_get_bytes(self, url: str) -> bytes:
        import requests
        r = requests.get(url, headers=self._auth_headers(), timeout=60)
        r.raise_for_status()
        return r.content

    def _paginate(self, url: str, params: dict | None = None) -> list:
        items = []
        while url:
            data = self._graph_get(url, params)
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            params = None  # nextLink includes params
        return items

    def _export_email(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "microsoft" / "email"
        out_dir.mkdir(parents=True, exist_ok=True)

        messages = self._paginate(
            "https://graph.microsoft.com/v1.0/me/messages",
            {"$top": "100", "$select": "id,subject,receivedDateTime"},
        )

        total = len(messages)
        if progress_cb:
            progress_cb(ExportProgress(DataType.EMAIL, 0, total, f"Found {total} emails"))

        for i, msg in enumerate(messages):
            # Get full MIME content
            try:
                content = self._graph_get_bytes(
                    f"https://graph.microsoft.com/v1.0/me/messages/{msg['id']}/$value"
                )
                subject = msg.get("subject", "no-subject")[:50].replace("/", "_")
                (out_dir / f"{i:06d}_{subject}.eml").write_bytes(content)
            except Exception as e:
                log.warning("Failed to download email %s: %s", msg.get("subject"), e)

            if progress_cb and (i % 10 == 0 or i == total - 1):
                progress_cb(ExportProgress(DataType.EMAIL, i + 1, total, f"Email {i+1}/{total}"))

        return out_dir

    def _export_contacts(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "microsoft" / "contacts"
        out_dir.mkdir(parents=True, exist_ok=True)

        contacts = self._paginate("https://graph.microsoft.com/v1.0/me/contacts")

        total = len(contacts)
        if progress_cb:
            progress_cb(ExportProgress(DataType.CONTACTS, 0, total, f"Found {total} contacts"))

        vcards = []
        for i, c in enumerate(contacts):
            vcard = "BEGIN:VCARD\nVERSION:3.0\n"
            display = c.get("displayName", "")
            given = c.get("givenName", "")
            surname = c.get("surname", "")
            vcard += f"FN:{display}\nN:{surname};{given};;;\n"
            for em in c.get("emailAddresses", []):
                vcard += f"EMAIL:{em.get('address', '')}\n"
            for ph in c.get("phones", []):
                vcard += f"TEL:{ph.get('number', '')}\n"
            vcard += "END:VCARD\n"
            vcards.append(vcard)

        (out_dir / "contacts.vcf").write_text("\n".join(vcards))
        if progress_cb:
            progress_cb(ExportProgress(DataType.CONTACTS, total, total, "Contacts exported"))
        return out_dir

    def _export_calendar(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "microsoft" / "calendar"
        out_dir.mkdir(parents=True, exist_ok=True)

        events = self._paginate(
            "https://graph.microsoft.com/v1.0/me/events",
            {"$top": "100"},
        )

        total = len(events)
        if progress_cb:
            progress_cb(ExportProgress(DataType.CALENDAR, 0, total, f"Found {total} events"))

        ical = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//DataScraper//EN\n"
        for ev in events:
            ical += "BEGIN:VEVENT\n"
            ical += f"SUMMARY:{ev.get('subject', '')}\n"
            start = ev.get("start", {})
            end = ev.get("end", {})
            if start.get("dateTime"):
                ical += f"DTSTART:{start['dateTime']}\n"
            if end.get("dateTime"):
                ical += f"DTEND:{end['dateTime']}\n"
            if ev.get("bodyPreview"):
                ical += f"DESCRIPTION:{ev['bodyPreview'][:200]}\n"
            ical += "END:VEVENT\n"
        ical += "END:VCALENDAR\n"

        (out_dir / "calendar.ics").write_text(ical)
        if progress_cb:
            progress_cb(ExportProgress(DataType.CALENDAR, total, total, "Calendar exported"))
        return out_dir

    def _export_drive(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "microsoft" / "onedrive"
        out_dir.mkdir(parents=True, exist_ok=True)

        items = self._paginate("https://graph.microsoft.com/v1.0/me/drive/root/children")
        # Filter to files only
        files = [item for item in items if "file" in item]

        total = len(files)
        if progress_cb:
            progress_cb(ExportProgress(DataType.DRIVE, 0, total, f"Found {total} files"))

        for i, f in enumerate(files):
            fname = f["name"].replace("/", "_")
            download_url = f.get("@microsoft.graph.downloadUrl")
            if download_url:
                try:
                    import requests
                    r = requests.get(download_url, timeout=60)
                    r.raise_for_status()
                    (out_dir / fname).write_bytes(r.content)
                except Exception as e:
                    log.warning("Failed to download %s: %s", fname, e)

            if progress_cb and (i % 5 == 0 or i == total - 1):
                progress_cb(ExportProgress(DataType.DRIVE, i + 1, total, f"OneDrive {i+1}/{total}"))

        return out_dir

    def disconnect(self) -> None:
        super().disconnect()
        self._access_token = None
        delete_token("microsoft")
