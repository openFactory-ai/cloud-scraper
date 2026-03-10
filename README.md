<p align="center">
  <img src="resources/icons/cloud-scraper.svg" alt="Cloud Scraper" width="120">
</p>

<h1 align="center">Cloud Scraper</h1>

<p align="center">
  Cloud data export GUI — download your personal data from Google, Microsoft, and Apple.<br>
  Built by <a href="https://openfactory.tech">OpenFactory</a>
</p>

## Features

- **Google** — Gmail, Contacts, Calendar, Drive, Photos
- **Microsoft** — Outlook Mail, Contacts, Calendar, OneDrive
- **Apple** *(experimental)* — Contacts, Calendar, iCloud Drive

Connect to one or more providers, select the data types you want, and export everything to a local folder. No data leaves your machine — exports go straight to disk.

## Install

### Option A: Debian/Ubuntu package

```bash
sudo apt install cloud-scraper
```

Available from the [OpenFactory package repository](https://openfactory.tech). Installs to `/opt/openfactory/cloud-scraper/` with a desktop entry and `/usr/bin/cloud-scraper` launcher.

### Option B: From source

```bash
git clone https://github.com/openFactory-ai/cloud-scraper.git
cd cloud-scraper
./setup.sh
```

The setup script installs system dependencies (GTK4, libadwaita, PyGObject) and creates a virtual environment with all Python dependencies.

## Usage

```bash
# If installed via package
cloud-scraper

# If running from source
python -m data_scraper
```

## Provider Setup

### Google

OAuth credentials are bundled with the .deb package. When running from source, place your OAuth credentials at one of:

- `~/.config/data-scraper/google-credentials.json`
- `./credentials/google.json`

Create credentials at [Google Cloud Console](https://console.cloud.google.com/apis/credentials) (Desktop app type).

### Microsoft

An embedded Azure AD client ID is included. To use your own, create `~/.config/data-scraper/microsoft.json`:

```json
{"client_id": "your-azure-app-client-id"}
```

Register an app at [Azure Portal](https://portal.azure.com) with the "Mobile and desktop applications" platform.

### Apple (experimental)

Uses Apple ID + app-specific password (no OAuth). Generate an app-specific password at [appleid.apple.com](https://appleid.apple.com/account/manage) under Sign-In and Security.

## Export Formats

| Data Type | Format |
|-----------|--------|
| Email | `.eml` files (one per message) |
| Contacts | `.vcf` (vCard 3.0) |
| Calendar | `.ics` (iCalendar) |
| Drive / OneDrive | Original files |
| Photos | Original files |

## Requirements

- Python 3.11+
- GTK4 + libadwaita
- PyGObject

### System packages

**Debian/Ubuntu:**
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-venv
```

**Fedora:**
```bash
sudo dnf install gtk4-devel libadwaita-devel python3-gobject
```

## License

[AGPL-3.0](LICENSE)
