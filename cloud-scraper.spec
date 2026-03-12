Name:           cloud-scraper
Version:        0.1.0
Release:        1%{?dist}
Summary:        Cloud data export GUI
License:        AGPL-3.0-only
URL:            https://github.com/openFactory-ai/cloud-scraper
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.11
Requires:       python3-pip
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       python3-systemd
Requires:       squashfs-tools
Requires:       xorriso

BuildRequires:  python3-devel

%description
Download your personal data from Google, Microsoft, and Apple
using official export APIs. Supports email, contacts, calendar,
drive/files, and photos with a GTK4/libadwaita interface.

%prep
%autosetup -n %{name}-%{version}

%build
# Nothing to build — venv is created at install time (%%post)

%install
# Application code
install -d %{buildroot}/opt/openfactory/cloud-scraper
cp -r data_scraper %{buildroot}/opt/openfactory/cloud-scraper/
cp -r resources %{buildroot}/opt/openfactory/cloud-scraper/
cp requirements.txt %{buildroot}/opt/openfactory/cloud-scraper/
cp -r vendor %{buildroot}/opt/openfactory/cloud-scraper/

# Privileged ISO helper script
install -m 755 data_scraper/iso_helper.sh %{buildroot}/opt/openfactory/cloud-scraper/iso-helper.sh

# OAuth credentials — local dir (dev builds) or OBS SOURCES dir
install -d %{buildroot}/opt/openfactory/cloud-scraper/credentials
for dir in credentials %{_sourcedir}; do
    for f in "$dir"/google.json "$dir"/microsoft.json; do
        if [ -f "$f" ]; then
            install -m 644 "$f" %{buildroot}/opt/openfactory/cloud-scraper/credentials/
        fi
    done
done

# Desktop entry
install -d %{buildroot}%{_datadir}/applications
install -m 644 cloud-scraper.desktop %{buildroot}%{_datadir}/applications/

# Launcher script
install -d %{buildroot}%{_bindir}
install -m 755 cloud-scraper.sh %{buildroot}%{_bindir}/cloud-scraper

%post
echo "Creating Python venv for Cloud Scraper..."
python3 -m venv --system-site-packages /opt/openfactory/cloud-scraper/venv
/opt/openfactory/cloud-scraper/venv/bin/pip install --no-index \
    --find-links=/opt/openfactory/cloud-scraper/vendor \
    -r /opt/openfactory/cloud-scraper/requirements.txt
echo "Cloud Scraper venv ready."

%preun
if [ "$1" = 0 ]; then
    rm -rf /opt/openfactory/cloud-scraper/venv
fi

%files
/opt/openfactory/cloud-scraper/
%{_datadir}/applications/cloud-scraper.desktop
%{_bindir}/cloud-scraper

%changelog
* Sat Mar 08 2026 OpenFactory <dev@openfactory.tech> - 0.1.0-1
- Initial RPM package
- Cloud data export GUI for Google, Microsoft, and Apple
- GTK4/libadwaita interface with provider cards
