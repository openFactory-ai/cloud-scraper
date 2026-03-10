"""Google data export provider — Gmail, Contacts, Calendar, Drive, Photos."""

import base64
import email
import json
import logging
from pathlib import Path

from data_scraper.providers.base import BaseProvider, DataType, ExportProgress, ProgressCallback
from data_scraper.utils.storage import store_token, load_token, delete_token

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

REDIRECT_PORT = 8085
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

# Embedded OAuth client config — Desktop app type (client secret is not confidential
# for installed/desktop apps per Google's documentation)
_EMBEDDED_CLIENT_CONFIG = {
    "installed": {
        "client_id": "",
        "client_secret": "",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

# Config file shipped with the deb package (not in git)
_SHIPPED_CONFIG_PATH = Path("/opt/cloud-scraper/credentials/google.json")


class GoogleProvider(BaseProvider):
    name = "Google"
    icon_name = "google"
    supported_data_types = [
        DataType.EMAIL,
        DataType.CONTACTS,
        DataType.CALENDAR,
        DataType.DRIVE,
        DataType.PHOTOS,
    ]

    def __init__(self):
        super().__init__()
        self._creds = None

    def authenticate(self) -> bool:
        self.last_error = None
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            self.last_error = "google-auth-oauthlib not installed"
            log.error(self.last_error)
            return False

        # Try loading stored token
        token_data = load_token("google")
        if token_data:
            try:
                self._creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                if self._creds.valid:
                    self._authenticated = True
                    self._fetch_user_email()
                    return True
                if self._creds.expired and self._creds.refresh_token:
                    from google.auth.transport.requests import Request
                    self._creds.refresh(Request())
                    self._save_creds()
                    self._authenticated = True
                    self._fetch_user_email()
                    return True
            except Exception as e:
                log.warning("Stored token invalid: %s", e)

        # Run OAuth flow
        client_config = self._get_client_config()
        if not client_config:
            self.last_error = (
                "No OAuth credentials found. Place google-credentials.json "
                "in ~/.config/data-scraper/"
            )
            log.error(self.last_error)
            return False

        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        try:
            self._creds = flow.run_local_server(
                port=REDIRECT_PORT,
                prompt="consent",
                open_browser=True,
            )
        except Exception as e:
            self.last_error = f"OAuth flow failed: {e}"
            log.error(self.last_error)
            return False

        self._save_creds()
        self._authenticated = True
        self._fetch_user_email()
        return True

    def _get_client_config(self) -> dict | None:
        """Load OAuth client config from shipped or user config file."""
        config_paths = [
            # User override
            Path.home() / ".config" / "data-scraper" / "google-credentials.json",
            # Shipped with deb package
            _SHIPPED_CONFIG_PATH,
        ]
        for p in config_paths:
            if p.exists():
                try:
                    data = json.loads(p.read_text())
                    log.info("Loaded Google OAuth config from %s", p)
                    return data
                except Exception as e:
                    log.warning("Failed to load %s: %s", p, e)

        log.error(
            "No Google OAuth config found. Expected at %s",
            _SHIPPED_CONFIG_PATH,
        )
        return None

    def _save_creds(self):
        if self._creds:
            store_token("google", json.loads(self._creds.to_json()))

    def _fetch_user_email(self):
        try:
            from googleapiclient.discovery import build
            service = build("oauth2", "v2", credentials=self._creds)
            info = service.userinfo().get().execute()
            self._user_email = info.get("email")
        except Exception as e:
            log.warning("Could not fetch user email: %s", e)

    def _build_service(self, api: str, version: str):
        from googleapiclient.discovery import build
        return build(api, version, credentials=self._creds)

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
            DataType.PHOTOS: self._export_photos,
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

    def _export_email(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "google" / "email"
        out_dir.mkdir(parents=True, exist_ok=True)

        service = self._build_service("gmail", "v1")
        # List all message IDs
        msg_ids = []
        request = service.users().messages().list(userId="me", maxResults=500)
        while request:
            response = request.execute()
            msg_ids.extend(m["id"] for m in response.get("messages", []))
            request = service.users().messages().list_next(request, response)

        total = len(msg_ids)
        if progress_cb:
            progress_cb(ExportProgress(DataType.EMAIL, 0, total, f"Found {total} emails"))

        for i, mid in enumerate(msg_ids):
            msg = service.users().messages().get(
                userId="me", id=mid, format="raw"
            ).execute()
            raw = base64.urlsafe_b64decode(msg["raw"])
            parsed = email.message_from_bytes(raw)
            subject = parsed.get("Subject", "no-subject")[:50].replace("/", "_")
            filename = f"{i:06d}_{subject}.eml"
            (out_dir / filename).write_bytes(raw)

            if progress_cb and (i % 10 == 0 or i == total - 1):
                progress_cb(ExportProgress(DataType.EMAIL, i + 1, total, f"Email {i+1}/{total}"))

        return out_dir

    def _export_contacts(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "google" / "contacts"
        out_dir.mkdir(parents=True, exist_ok=True)

        service = self._build_service("people", "v1")
        contacts = []
        page_token = None

        while True:
            response = service.people().connections().list(
                resourceName="people/me",
                pageSize=1000,
                personFields="names,emailAddresses,phoneNumbers,addresses",
                pageToken=page_token,
            ).execute()
            contacts.extend(response.get("connections", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        total = len(contacts)
        if progress_cb:
            progress_cb(ExportProgress(DataType.CONTACTS, 0, total, f"Found {total} contacts"))

        # Write as vCard
        vcards = []
        for i, contact in enumerate(contacts):
            vcard = "BEGIN:VCARD\nVERSION:3.0\n"
            names = contact.get("names", [{}])
            if names:
                n = names[0]
                display = n.get("displayName", "")
                family = n.get("familyName", "")
                given = n.get("givenName", "")
                vcard += f"FN:{display}\nN:{family};{given};;;\n"
            for em in contact.get("emailAddresses", []):
                vcard += f"EMAIL:{em['value']}\n"
            for ph in contact.get("phoneNumbers", []):
                vcard += f"TEL:{ph['value']}\n"
            vcard += "END:VCARD\n"
            vcards.append(vcard)

            if progress_cb and (i % 50 == 0):
                progress_cb(ExportProgress(DataType.CONTACTS, i + 1, total, f"Contact {i+1}/{total}"))

        (out_dir / "contacts.vcf").write_text("\n".join(vcards))
        if progress_cb:
            progress_cb(ExportProgress(DataType.CONTACTS, total, total, "Contacts exported"))
        return out_dir

    def _export_calendar(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "google" / "calendar"
        out_dir.mkdir(parents=True, exist_ok=True)

        service = self._build_service("calendar", "v3")
        calendars = service.calendarList().list().execute().get("items", [])

        total = len(calendars)
        if progress_cb:
            progress_cb(ExportProgress(DataType.CALENDAR, 0, total, f"Found {total} calendars"))

        for i, cal in enumerate(calendars):
            cal_id = cal["id"]
            cal_name = cal.get("summary", cal_id).replace("/", "_")
            events = []
            page_token = None

            while True:
                response = service.events().list(
                    calendarId=cal_id, maxResults=2500, pageToken=page_token
                ).execute()
                events.extend(response.get("items", []))
                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            # Write iCal
            ical = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//DataScraper//EN\n"
            ical += f"X-WR-CALNAME:{cal.get('summary', '')}\n"
            for ev in events:
                ical += "BEGIN:VEVENT\n"
                ical += f"SUMMARY:{ev.get('summary', '')}\n"
                start = ev.get("start", {})
                end = ev.get("end", {})
                if "dateTime" in start:
                    ical += f"DTSTART:{start['dateTime']}\n"
                elif "date" in start:
                    ical += f"DTSTART;VALUE=DATE:{start['date']}\n"
                if "dateTime" in end:
                    ical += f"DTEND:{end['dateTime']}\n"
                elif "date" in end:
                    ical += f"DTEND;VALUE=DATE:{end['date']}\n"
                if ev.get("description"):
                    ical += f"DESCRIPTION:{ev['description'][:200]}\n"
                ical += "END:VEVENT\n"
            ical += "END:VCALENDAR\n"
            (out_dir / f"{cal_name}.ics").write_text(ical)

            if progress_cb:
                progress_cb(ExportProgress(DataType.CALENDAR, i + 1, total, f"Calendar {i+1}/{total}"))

        return out_dir

    def _export_drive(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "google" / "drive"
        out_dir.mkdir(parents=True, exist_ok=True)

        service = self._build_service("drive", "v3")
        files = []
        page_token = None

        while True:
            response = service.files().list(
                pageSize=1000,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                q="trashed=false",
            ).execute()
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        total = len(files)
        if progress_cb:
            progress_cb(ExportProgress(DataType.DRIVE, 0, total, f"Found {total} files"))

        google_mime_exports = {
            "application/vnd.google-apps.document": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
            ),
            "application/vnd.google-apps.spreadsheet": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"
            ),
            "application/vnd.google-apps.presentation": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
            ),
        }

        for i, f in enumerate(files):
            fname = f["name"].replace("/", "_")
            mime = f["mimeType"]

            try:
                if mime.startswith("application/vnd.google-apps."):
                    if mime in google_mime_exports:
                        export_mime, ext = google_mime_exports[mime]
                        content = service.files().export(
                            fileId=f["id"], mimeType=export_mime
                        ).execute()
                        (out_dir / f"{fname}{ext}").write_bytes(content)
                    # Skip other Google-native types (forms, sites, etc.)
                else:
                    from googleapiclient.http import MediaIoBaseDownload
                    import io
                    request = service.files().get_media(fileId=f["id"])
                    buf = io.BytesIO()
                    downloader = MediaIoBaseDownload(buf, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                    (out_dir / fname).write_bytes(buf.getvalue())
            except Exception as e:
                log.warning("Failed to download %s: %s", fname, e)

            if progress_cb and (i % 5 == 0 or i == total - 1):
                progress_cb(ExportProgress(DataType.DRIVE, i + 1, total, f"Drive {i+1}/{total}"))

        return out_dir

    def _export_photos(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        out_dir = dest_dir / "google" / "photos"
        out_dir.mkdir(parents=True, exist_ok=True)

        import requests as req

        service = self._build_service("photoslibrary", "v1")
        items = []
        page_token = None

        while True:
            body = {"pageSize": 100}
            if page_token:
                body["pageToken"] = page_token
            response = service.mediaItems().list(**body).execute()
            items.extend(response.get("mediaItems", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        total = len(items)
        if progress_cb:
            progress_cb(ExportProgress(DataType.PHOTOS, 0, total, f"Found {total} photos/videos"))

        for i, item in enumerate(items):
            fname = item.get("filename", f"photo_{i}")
            base_url = item["baseUrl"]
            # Append =d for full resolution download
            url = f"{base_url}=d"
            try:
                r = req.get(url, timeout=60)
                r.raise_for_status()
                (out_dir / fname).write_bytes(r.content)
            except Exception as e:
                log.warning("Failed to download photo %s: %s", fname, e)

            if progress_cb and (i % 5 == 0 or i == total - 1):
                progress_cb(ExportProgress(DataType.PHOTOS, i + 1, total, f"Photo {i+1}/{total}"))

        return out_dir

    def disconnect(self) -> None:
        super().disconnect()
        self._creds = None
        delete_token("google")
