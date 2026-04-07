"""JSON scan-result persistence (cache).

Functions in this module are stateless I/O — they accept and return plain data
and have no dependency on ``PackageManager`` or any adapter class.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional


def default_cache_path() -> str:
    """Return the default cache file path (``~/.wincoman/state.json``)."""
    return os.path.join(os.path.expanduser("~"), ".wincoman", "state.json")


def save_cache(
    path: str,
    unmanaged_apps: list,
    matches: list,
) -> None:
    """Persist *unmanaged_apps* and *matches* to *path* as JSON.

    Creates parent directories if they do not exist.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "unmanaged_apps": unmanaged_apps,
        "matches": matches,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    logging.info(f"Cache saved: {path}")


def load_cache(path: str) -> Optional[tuple[list, list]]:
    """Load scan results from *path*.

    Returns:
        ``(unmanaged_apps, matches)`` tuple on success, or ``None`` if the
        file is missing, unreadable, or contains invalid JSON.
    """
    if not os.path.exists(path):
        logging.warning(f"Cache file not found: {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
        unmanaged_apps = state.get("unmanaged_apps", [])
        matches = state.get("matches", [])
        ts = state.get("timestamp", "unknown")
        logging.info(f"Loaded cache from {path} (scanned: {ts})")
        return unmanaged_apps, matches
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logging.warning(f"Failed to load cache: {exc}")
        return None
