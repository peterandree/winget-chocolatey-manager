"""Scoop package manager adapter.

Implements :class:`BasePackageManager` for Scoop.  Scoop is a list-only source
(no remote search API from the CLI).  ``is_available()`` returns ``False``
gracefully when Scoop is not on PATH.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from wincoman.matchers.base import BasePackageManager
from wincoman.scoring import normalize_name
from wincoman.shell import run_command

# Matches ANSI escape sequences (colours, bold, reset, etc.)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class ScoopManager(BasePackageManager):
    """Adapter for the Scoop package manager."""

    def __init__(self, runner: Optional[Callable] = None) -> None:
        self._runner = runner or run_command
        self._cache: Optional[set[str]] = None
        self._available: Optional[bool] = None
        self._normalised_cache: Optional[set[str]] = None

    @property
    def name(self) -> str:
        return "scoop"

    def is_available(self) -> bool:
        """Return True when scoop is on PATH and responds."""
        if self._available is None:
            _, _, code = self._runner(["scoop", "--version"], timeout=10)
            self._available = code == 0
        return self._available

    def list_managed(self) -> set[str]:
        """Return normalised names of all Scoop-installed packages."""
        return {normalize_name(n) for n in self._raw_names()}

    def is_managed(self, display_name: str) -> bool:
        """Return True if *display_name* matches a Scoop package."""
        raw = self._raw_names()
        name_lower = display_name.lower()
        if name_lower in raw:
            return True
        norm = normalize_name(display_name)
        return norm in self._get_normalised_set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_normalised_set(self) -> set[str]:
        """Return cached set of normalised package names."""
        if self._normalised_cache is None:
            self._normalised_cache = {normalize_name(n) for n in self._raw_names()}
        return self._normalised_cache

    def _raw_names(self) -> set[str]:
        """Return cached set of raw (un-normalised) package names."""
        if self._cache is not None:
            return self._cache

        stdout, stderr, code = self._runner(["scoop", "list"], timeout=30)
        if code != 0:
            logging.info("Scoop not found or unavailable — skipping Scoop check.")
            self._cache = set()
            return self._cache

        # Scoop may emit ANSI colour codes in the header; strip them first.
        # Data lines (app names) are plain text.
        _SKIP = {"name", "----", "installed", "apps:"}
        names: set[str] = set()
        for raw_line in stdout.split("\n"):
            line = _strip_ansi(raw_line).strip()
            parts = line.split()
            if not parts:
                continue
            name = parts[0].lower()
            # Skip header, separator, and section-title tokens
            if name in _SKIP or name.startswith("-"):
                continue
            names.add(name)

        self._cache = names
        if names:
            logging.info(f"Found {len(names)} packages in Scoop")
        return self._cache
