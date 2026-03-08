"""Token storage via keyring for secure credential persistence."""

import json
import logging

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

from data_scraper import APP_ID

log = logging.getLogger(__name__)

_SERVICE = APP_ID


def store_token(provider: str, token_data: dict) -> None:
    """Store an OAuth token for a provider."""
    if not HAS_KEYRING:
        log.warning("keyring not available — tokens will not persist across sessions")
        return
    keyring.set_password(_SERVICE, provider, json.dumps(token_data))


def load_token(provider: str) -> dict | None:
    """Load a stored OAuth token for a provider."""
    if not HAS_KEYRING:
        return None
    try:
        data = keyring.get_password(_SERVICE, provider)
        if data:
            return json.loads(data)
    except Exception as e:
        log.warning("Failed to load token for %s: %s", provider, e)
    return None


def delete_token(provider: str) -> None:
    """Remove a stored token for a provider."""
    if not HAS_KEYRING:
        return
    try:
        keyring.delete_password(_SERVICE, provider)
    except Exception:
        pass
