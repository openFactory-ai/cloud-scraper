#!/bin/bash
export PYTHONPATH=/opt/cloud-scraper
exec /opt/cloud-scraper/venv/bin/python3 -m data_scraper "$@"
