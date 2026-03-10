"""Apple data export provider — Contacts, Calendar, iCloud Drive, Photos.

This provider uses undocumented iCloud APIs and is marked as experimental.
Requires an app-specific password generated at appleid.apple.com.
"""

import json
import logging
from pathlib import Path

import requests

from data_scraper.providers.base import BaseProvider, DataType, ExportProgress, ProgressCallback
from data_scraper.utils.storage import store_token, load_token, delete_token

log = logging.getLogger(__name__)

ICLOUD_AUTH_URL = "https://idmsa.apple.com/appleauth/auth/signin"
ICLOUD_SETUP_URL = "https://setup.icloud.com/setup/ws/1"
CARDDAV_URL = "https://contacts.icloud.com"
CALDAV_URL = "https://caldav.icloud.com"


class AppleProvider(BaseProvider):
    name = "Apple"
    icon_name = "apple"
    experimental = True
    supported_data_types = [
        DataType.CONTACTS,
        DataType.CALENDAR,
        DataType.DRIVE,
        DataType.PHOTOS,
    ]

    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._apple_id: str | None = None
        self._password: str | None = None
        self._dsid: str | None = None
        self._webservices: dict = {}

    def authenticate(self) -> bool:
        """Authenticate with Apple ID + app-specific password.

        Since Apple doesn't provide OAuth, this requires the user to generate
        an app-specific password at https://appleid.apple.com/account/manage
        """
        self.last_error = None
        # Try stored credentials
        token_data = load_token("apple")
        if token_data:
            self._apple_id = token_data.get("apple_id")
            self._password = token_data.get("password")
            if self._apple_id and self._password:
                if self._icloud_login():
                    self._authenticated = True
                    self._user_email = self._apple_id
                    return True
                self.last_error = "iCloud login failed — check your app-specific password"

        # Need credentials from UI — they'll be set via set_credentials()
        if not self.last_error:
            self.last_error = "Enter your Apple ID and app-specific password"
        log.info("Apple auth: %s", self.last_error)
        return False

    def set_credentials(self, apple_id: str, password: str) -> bool:
        """Set Apple ID credentials and attempt login."""
        self.last_error = None
        self._apple_id = apple_id
        self._password = password

        if self._icloud_login():
            store_token("apple", {"apple_id": apple_id, "password": password})
            self._authenticated = True
            self._user_email = apple_id
            return True
        if not self.last_error:
            self.last_error = "iCloud login failed"
        return False

    def _icloud_login(self) -> bool:
        """Authenticate with iCloud web services."""
        try:
            headers = {
                "Origin": "https://www.icloud.com",
                "Referer": "https://www.icloud.com/",
                "Content-Type": "application/json",
            }
            data = {
                "apple_id": self._apple_id,
                "password": self._password,
                "extended_login": True,
            }
            r = self._session.post(
                ICLOUD_AUTH_URL,
                json=data,
                headers=headers,
                timeout=30,
            )
            if r.status_code not in (200, 409):
                self.last_error = f"iCloud auth failed (HTTP {r.status_code})"
                log.error(self.last_error)
                return False

            # Get webservice URLs
            r2 = self._session.get(
                f"{ICLOUD_SETUP_URL}/validate",
                headers=headers,
                timeout=30,
            )
            if r2.status_code == 200:
                data = r2.json()
                self._dsid = data.get("dsInfo", {}).get("dsid")
                self._webservices = data.get("webservices", {})
                return True

        except Exception as e:
            self.last_error = f"iCloud login failed: {e}"
            log.error(self.last_error)
        return False

    def export_data(
        self,
        data_types: list[DataType],
        dest_dir: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> dict[DataType, Path]:
        results = {}
        exporters = {
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

    def _export_contacts(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        """Export contacts via CardDAV."""
        out_dir = dest_dir / "apple" / "contacts"
        out_dir.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(ExportProgress(DataType.CONTACTS, 0, 1, "Fetching contacts via CardDAV..."))

        try:
            # PROPFIND to discover address books
            headers = {"Depth": "1", "Content-Type": "application/xml"}
            body = """<?xml version="1.0" encoding="UTF-8"?>
<A:propfind xmlns:A="DAV:">
  <A:prop>
    <A:resourcetype/>
    <A:displayname/>
  </A:prop>
</A:propfind>"""

            r = self._session.request(
                "PROPFIND",
                f"{CARDDAV_URL}/{self._dsid}/carddavhome/card/",
                headers=headers,
                data=body,
                auth=(self._apple_id, self._password),
                timeout=30,
            )

            if r.status_code in (207, 200):
                # REPORT to get all vCards
                report_body = """<?xml version="1.0" encoding="UTF-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data/>
  </D:prop>
</C:addressbook-query>"""

                r2 = self._session.request(
                    "REPORT",
                    f"{CARDDAV_URL}/{self._dsid}/carddavhome/card/",
                    headers={"Depth": "1", "Content-Type": "application/xml"},
                    data=report_body,
                    auth=(self._apple_id, self._password),
                    timeout=60,
                )

                if r2.status_code in (207, 200):
                    (out_dir / "contacts.vcf").write_text(r2.text)

        except Exception as e:
            log.error("CardDAV export failed: %s", e)

        if progress_cb:
            progress_cb(ExportProgress(DataType.CONTACTS, 1, 1, "Contacts exported"))
        return out_dir

    def _export_calendar(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        """Export calendars via CalDAV."""
        out_dir = dest_dir / "apple" / "calendar"
        out_dir.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(ExportProgress(DataType.CALENDAR, 0, 1, "Fetching calendars via CalDAV..."))

        try:
            headers = {"Depth": "1", "Content-Type": "application/xml"}
            body = """<?xml version="1.0" encoding="UTF-8"?>
<A:propfind xmlns:A="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <A:prop>
    <A:resourcetype/>
    <A:displayname/>
    <C:calendar-data/>
  </A:prop>
</A:propfind>"""

            r = self._session.request(
                "PROPFIND",
                f"{CALDAV_URL}/{self._dsid}/calendars/",
                headers=headers,
                data=body,
                auth=(self._apple_id, self._password),
                timeout=30,
            )

            if r.status_code in (207, 200):
                (out_dir / "calendars.xml").write_text(r.text)

        except Exception as e:
            log.error("CalDAV export failed: %s", e)

        if progress_cb:
            progress_cb(ExportProgress(DataType.CALENDAR, 1, 1, "Calendar exported"))
        return out_dir

    def _export_drive(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        """Export iCloud Drive files via iCloud web API."""
        out_dir = dest_dir / "apple" / "drive"
        out_dir.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(ExportProgress(DataType.DRIVE, 0, 1, "Fetching iCloud Drive..."))

        drive_ws = self._webservices.get("drivews", {})
        drive_url = drive_ws.get("url")
        if not drive_url:
            log.warning("iCloud Drive webservice URL not available")
            if progress_cb:
                progress_cb(ExportProgress(DataType.DRIVE, 0, 0, "iCloud Drive not available"))
            return out_dir

        try:
            # List root folder
            r = self._session.post(
                f"{drive_url}/retrieveItemDetailsInFolders",
                json=[{"drivewsid": "FOLDER::com.apple.CloudDocs::root", "partialData": False}],
                timeout=30,
            )
            if r.status_code != 200:
                log.warning("Failed to list iCloud Drive: %s", r.status_code)
                return out_dir

            items = r.json()[0].get("items", [])
            total = len(items)
            if progress_cb:
                progress_cb(ExportProgress(DataType.DRIVE, 0, total, f"Found {total} items"))

            doc_ws = self._webservices.get("docws", {}).get("url", "")
            for i, item in enumerate(items):
                if item.get("type") == "FILE":
                    zone = item.get("zone", "")
                    doc_id = item.get("docwsid", "")
                    fname = item.get("name", f"file_{i}")
                    ext = item.get("extension", "")
                    if ext:
                        fname = f"{fname}.{ext}"
                    try:
                        dl = self._session.get(
                            f"{doc_ws}/ws/com.apple.CloudDocs/download/by_id",
                            params={"document_id": doc_id},
                            timeout=60,
                        )
                        if dl.status_code == 200:
                            dl_data = dl.json()
                            pkg_url = dl_data.get("data_token", {}).get("url")
                            if pkg_url:
                                content = self._session.get(pkg_url, timeout=120).content
                                (out_dir / fname.replace("/", "_")).write_bytes(content)
                    except Exception as e:
                        log.warning("Failed to download %s: %s", fname, e)

                if progress_cb and (i % 5 == 0 or i == total - 1):
                    progress_cb(ExportProgress(DataType.DRIVE, i + 1, total, f"Drive {i+1}/{total}"))

        except Exception as e:
            log.error("iCloud Drive export failed: %s", e)

        return out_dir

    def _export_photos(self, dest_dir: Path, progress_cb: ProgressCallback | None) -> Path:
        """Export iCloud Photos via iCloud web API."""
        out_dir = dest_dir / "apple" / "photos"
        out_dir.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(ExportProgress(DataType.PHOTOS, 0, 1, "Fetching iCloud Photos..."))

        ckdb_ws = self._webservices.get("ckdatabasews", {})
        ckdb_url = ckdb_ws.get("url")
        if not ckdb_url:
            log.warning("iCloud Photos webservice URL not available")
            if progress_cb:
                progress_cb(ExportProgress(DataType.PHOTOS, 0, 0, "iCloud Photos not available"))
            return out_dir

        try:
            # Query CloudKit for photos
            query_url = f"{ckdb_url}/database/1/com.apple.photos.cloud/production/private/records/query"
            query = {
                "query": {
                    "recordType": "CPLAsset",
                    "filterBy": [],
                },
                "resultsLimit": 200,
            }
            r = self._session.post(query_url, json=query, timeout=30)
            if r.status_code != 200:
                log.warning("Failed to query iCloud Photos: %s", r.status_code)
                return out_dir

            records = r.json().get("records", [])
            total = len(records)
            if progress_cb:
                progress_cb(ExportProgress(DataType.PHOTOS, 0, total, f"Found {total} photos"))

            for i, record in enumerate(records):
                fields = record.get("fields", {})
                filename = fields.get("filenameEnc", {}).get("value", f"photo_{i}.jpg")
                res_field = fields.get("resOriginalRes", {})
                download_url = res_field.get("value", {}).get("downloadURL")

                if download_url:
                    try:
                        content = self._session.get(download_url, timeout=120).content
                        (out_dir / filename.replace("/", "_")).write_bytes(content)
                    except Exception as e:
                        log.warning("Failed to download photo %s: %s", filename, e)

                if progress_cb and (i % 5 == 0 or i == total - 1):
                    progress_cb(ExportProgress(DataType.PHOTOS, i + 1, total, f"Photo {i+1}/{total}"))

        except Exception as e:
            log.error("iCloud Photos export failed: %s", e)

        return out_dir

    def disconnect(self) -> None:
        super().disconnect()
        self._dsid = None
        self._webservices = {}
        self._session = requests.Session()
        delete_token("apple")
