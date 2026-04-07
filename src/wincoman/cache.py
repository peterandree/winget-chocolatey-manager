"""JSON scan-result persistence (cache).

Functions in this module are stateless I/O — they accept and return plain data
and have no dependency on ``PackageManager`` or any adapter class.

Cache schema (v2):
    {
      "schema_version": 2,
      "timestamp": "<ISO-8601>",
      "unmanaged_apps": [...],
      "candidates": [
        {
          "app_name": str, "app_version": str,
          "primary": {PackageMatch fields},
          "alternatives": [{PackageMatch fields}, ...]
        }, ...
      ]
    }

v1 files (with a ``"matches"`` key) are read as a flat list of
:class:`PackageMatch` objects and wrapped in bare :class:`AppCandidates`
for backward compatibility.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from wincoman.matchers.base import AppCandidates, PackageMatch

_SCHEMA_VERSION = 2


def _match_to_dict(m: PackageMatch) -> dict:
    return {
        "app_name": m.app_name,
        "app_version": m.app_version,
        "pkg_id": m.pkg_id,
        "pkg_version": m.pkg_version,
        "version_mismatch": m.version_mismatch,
        "manager": m.manager,
    }


def _dict_to_match(d: dict) -> PackageMatch:
    return PackageMatch(
        app_name=d["app_name"],
        app_version=d.get("app_version", ""),
        pkg_id=d["pkg_id"],
        pkg_version=d.get("pkg_version", ""),
        version_mismatch=d.get("version_mismatch", False),
        manager=d.get("manager", "chocolatey"),
    )


def _candidates_to_list(candidates: list[AppCandidates]) -> list[dict]:
    result = []
    for c in candidates:
        result.append({
            "app_name": c.app_name,
            "app_version": c.app_version,
            "primary": _match_to_dict(c.primary),
            "alternatives": [_match_to_dict(a) for a in c.alternatives],
        })
    return result


def _list_to_candidates(data: list[dict]) -> list[AppCandidates]:
    result = []
    for item in data:
        primary = _dict_to_match(item["primary"])
        alternatives = [_dict_to_match(a) for a in item.get("alternatives", [])]
        result.append(
            AppCandidates(
                app_name=item["app_name"],
                app_version=item.get("app_version", ""),
                primary=primary,
                alternatives=alternatives,
            )
        )
    return result


def default_cache_path() -> str:
    """Return the default cache file path (``~/.wincoman/state.json``)."""
    return os.path.join(os.path.expanduser("~"), ".wincoman", "state.json")


def save_cache(
    path: str,
    unmanaged_apps: list,
    candidates: list[AppCandidates],
) -> None:
    """Persist *unmanaged_apps* and *candidates* to *path* as JSON (schema v2).

    Creates parent directories if they do not exist.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state = {
        "schema_version": _SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "unmanaged_apps": unmanaged_apps,
        "candidates": _candidates_to_list(candidates),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    logging.info(f"Cache saved: {path}")


def load_cache(path: str) -> Optional[tuple[list, list[AppCandidates]]]:
    """Load scan results from *path*.

    Handles both schema v2 (``candidates`` key) and legacy v1 (``matches``
    key with flat :class:`PackageMatch` dicts).

    Returns:
        ``(unmanaged_apps, candidates)`` tuple on success, or ``None`` if the
        file is missing, unreadable, or contains invalid JSON.
    """
    if not os.path.exists(path):
        logging.warning(f"Cache file not found: {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
        unmanaged_apps = state.get("unmanaged_apps", [])
        ts = state.get("timestamp", "unknown")
        schema = state.get("schema_version", 1)

        if schema >= 2 and "candidates" in state:
            candidates = _list_to_candidates(state["candidates"])
        elif "matches" in state:
            # v1 compat: flat list of PackageMatch dicts → wrap in AppCandidates
            logging.info("Loading v1 cache; wrapping matches as AppCandidates")
            candidates = []
            for m in state["matches"]:
                pm = _dict_to_match(m)
                candidates.append(
                    AppCandidates(
                        app_name=pm.app_name,
                        app_version=pm.app_version,
                        primary=pm,
                    )
                )
        else:
            logging.warning("Cache has no recognized matches key")
            return None

        logging.info(f"Loaded cache from {path} (scanned: {ts}, schema v{schema})")
        return unmanaged_apps, candidates
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logging.warning(f"Failed to load cache: {exc}")
        return None
