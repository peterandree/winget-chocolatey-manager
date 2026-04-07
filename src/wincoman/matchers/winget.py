"""WinGet package manager adapter.

Implements :class:`BasePackageManager` for WinGet (Windows Package Manager).
WinGet is a list-only source — it has no remote search API accessible from
the command line without interactive output.
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from wincoman.matchers.base import BasePackageManager
from wincoman.scoring import fuzzy_score, normalize_name
from wincoman.shell import run_command

_DEFAULT_MIN_SCORE = 60


class WinGetManager(BasePackageManager):
    """Adapter for the Windows Package Manager (winget)."""

    def __init__(
        self,
        min_score: int = _DEFAULT_MIN_SCORE,
        runner: Optional[Callable] = None,
    ) -> None:
        self._min_score = min_score
        self._runner = runner or run_command
        self._cache: Optional[dict[str, str]] = None  # name_lower -> id
        self._available: Optional[bool] = None

    @property
    def name(self) -> str:
        return "winget"

    def is_available(self) -> bool:
        """Return True when winget is on PATH and responds."""
        if self._available is None:
            _, _, code = self._runner(["winget", "--version"])
            self._available = code == 0
        return self._available

    def list_managed(self) -> set[str]:
        """Return normalised names of all WinGet-managed packages."""
        return {normalize_name(n) for n in self._get_name_map()}

    def is_managed(self, display_name: str) -> bool:
        """Return True if *display_name* matches a WinGet-managed package."""
        name_map = self._get_name_map()
        name_lower = display_name.lower()
        if name_lower in name_map:
            return True
        for wg_name in name_map:
            if fuzzy_score(display_name, wg_name) >= self._min_score:
                return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_name_map(self) -> dict[str, str]:
        """Return a cached ``{name_lower: id}`` map from winget list."""
        if self._cache is not None:
            return self._cache

        stdout, stderr, code = self._runner(
            ["winget", "list", "--output", "json", "--accept-source-agreements"]
        )
        if code != 0:
            logging.warning(f"winget list failed: {stderr}")
            self._cache = {}
            return self._cache

        try:
            packages = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            logging.warning("winget list returned invalid JSON")
            self._cache = {}
            return self._cache

        result: dict[str, str] = {}
        for pkg in packages:
            name = (pkg.get("Name") or "").strip()
            if name:
                result[name.lower()] = pkg.get("Id", "")
        self._cache = result
        return self._cache
