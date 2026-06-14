"""Constants for the AwoX Smart Plug (Revogi) integration."""

from __future__ import annotations

DOMAIN = "awox_plug"

CONF_ADDRESS = "address"

DEFAULT_NAME = "AwoX Smart Plug"
MODEL = "SMP-B16-GR"
MANUFACTURER = "AwoX / Revogi"

# Polling interval (seconds). Adjustable from the integration's Options.
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 600
