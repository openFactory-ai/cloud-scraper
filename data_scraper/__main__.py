"""Entry point for data-scraper."""

import logging
import sys


def _setup_logging():
    """Configure logging to systemd journal (with stderr fallback)."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    try:
        from systemd.journal import JournalHandler
        handler = JournalHandler(SYSLOG_IDENTIFIER="cloud-scraper")
    except ImportError:
        handler = logging.StreamHandler(sys.stderr)

    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(name)s: %(message)s")
    handler.setFormatter(fmt)
    root.addHandler(handler)


def main():
    _setup_logging()
    from data_scraper.app import DataScraperApp

    app = DataScraperApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
