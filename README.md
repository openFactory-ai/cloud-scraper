<p align="center">
  <img src="resources/icons/cloud-scraper.svg" alt="Cloud Scraper" width="120">
</p>

<h1 align="center">Cloud Scraper</h1>

<p align="center">
  Cloud data export GUI — download your personal data from Google, Microsoft, and Apple.<br>
  Built by <a href="https://openfactory.tech">OpenFactory</a>
</p>

## Requirements

- Python 3.11+
- GTK4 + libadwaita (system packages)
- Python dependencies (see pyproject.toml)

### System packages (Fedora)

```bash
sudo dnf install gtk4-devel libadwaita-devel python3-gobject
```

### Python dependencies

```bash
pip install google-api-python-client google-auth-oauthlib msal msgraph-sdk requests keyring icalendar
```

## Usage

```bash
cd ~/Documents/vyatta/cloud-scraper
python -m data_scraper
```

## Provider Setup

### Google
Place your OAuth credentials at one of:
- `./credentials.json`
- `~/.config/data-scraper/google-credentials.json`

Create credentials at https://console.cloud.google.com/apis/credentials

### Microsoft
Create `~/.config/data-scraper/microsoft.json`:
```json
{"client_id": "your-azure-app-client-id"}
```

Register an app at https://portal.azure.com

### Apple
Uses Apple ID + app-specific password (no OAuth).
Generate an app-specific password at https://appleid.apple.com/account/manage
