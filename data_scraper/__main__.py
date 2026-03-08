"""Entry point for data-scraper."""

import sys


def main():
    from data_scraper.app import DataScraperApp

    app = DataScraperApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
