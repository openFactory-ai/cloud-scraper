#!/bin/bash
export PYTHONPATH=/opt/openfactory/cloud-scraper
exec /opt/openfactory/cloud-scraper/venv/bin/python3 -m data_scraper "$@"
