#!/bin/bash
# Cloud Scraper — quick setup script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "=== Cloud Scraper Setup ==="

# Install system dependencies
if command -v dnf &>/dev/null; then
    echo "Installing system packages (Fedora)..."
    sudo dnf install -y gtk4-devel libadwaita-devel python3-gobject python3-devel
elif command -v apt-get &>/dev/null; then
    echo "Installing system packages (Debian/Ubuntu)..."
    sudo apt-get update
    sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-venv python3-dev
else
    echo "Unsupported package manager. Install GTK4, libadwaita, and PyGObject manually."
    exit 1
fi

# Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv --system-site-packages "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# Install Python dependencies
echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "=== Setup complete ==="
echo "Run with: $VENV_DIR/bin/python -m data_scraper"
