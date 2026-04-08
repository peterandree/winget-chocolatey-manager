"""PowerShell Gallery (PSGallery) package manager adapter.

Detects PowerShell modules installed via ``Install-Module`` (PowerShellGet).
Each such module has a ``PSGetModuleInfo.xml`` marker file that records its
name, version, and source repository.

This adapter is read-only (no install support); it only classifies whether
an installed program corresponds to a PSGallery module.  In practice the
overlap with the Windows registry is small — modules typically don't appear
in Add/Remove Programs — but edge cases like ``Microsoft.WinGet.Client``
do surface there via UniGetUI.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

from wincoman.matchers.base import BasePackageManager
from wincoman.scoring import normalize_name

# Standard PowerShell module search paths (same order as $env:PSModulePath)
_DEFAULT_MODULE_PATHS: list[Path] = [
    Path(os.path.expanduser("~")) / "Documents" / "WindowsPowerShell" / "Modules",
    Path(os.path.expanduser("~")) / "Documents" / "PowerShell" / "Modules",
    Path("C:/Program Files/WindowsPowerShell/Modules"),
    Path("C:/Program Files/PowerShell/Modules"),
]

_PSGALLERY_MARKER = "PSGetModuleInfo.xml"


class PSGalleryManager(BasePackageManager):
    """Adapter for PowerShell modules installed from PSGallery via Install-Module."""

    def __init__(
        self,
        module_paths: Optional[list[Path]] = None,
        runner: Optional[Callable] = None,
    ) -> None:
        # module_paths allows tests to inject a custom search root
        self._module_paths = module_paths if module_paths is not None else _DEFAULT_MODULE_PATHS
        self._runner = runner  # unused for detection, kept for future install support
        self._cache: Optional[dict[str, str]] = None  # normalized_name -> module_name
        self._available: Optional[bool] = None

    @property
    def name(self) -> str:
        return "psgallery"

    def is_available(self) -> bool:
        """Return True when at least one PSGallery module path exists."""
        if self._available is None:
            self._available = any(p.exists() for p in self._module_paths)
        return self._available

    def list_managed(self) -> set[str]:
        """Return normalised names of all PSGallery-installed modules."""
        return set(self._get_name_map().keys())

    def is_managed(self, display_name: str) -> bool:
        """Return True if *display_name* matches an installed PSGallery module."""
        name_map = self._get_name_map()
        norm = normalize_name(display_name)
        if norm in name_map:
            return True
        # Also try exact lowercase (module names are usually clean)
        return display_name.lower() in name_map

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_name_map(self) -> dict[str, str]:
        """Return ``{normalized_name: original_module_name}`` for all PSGallery modules.

        Scans every ``PSGetModuleInfo.xml`` under the configured module paths.
        Only modules whose ``Repository`` field contains "PSGallery" (case-
        insensitive) are included.
        """
        if self._cache is not None:
            return self._cache

        result: dict[str, str] = {}
        for base in self._module_paths:
            if not base.exists():
                continue
            for marker in base.rglob(_PSGALLERY_MARKER):
                module_name = self._read_module_name(marker)
                if module_name:
                    norm = normalize_name(module_name)
                    result[norm] = module_name
                    result.setdefault(module_name.lower(), module_name)

        self._cache = result
        if result:
            unique = {v for v in result.values()}
            logging.info(f"Found {len(unique)} PSGallery modules")
        return self._cache

    @staticmethod
    def _read_module_name(xml_path: Path) -> Optional[str]:
        """Parse a PSGetModuleInfo.xml and return the module Name, or None on error.

        Uses a simple line-scan rather than a full XML parser to avoid a
        dependency on xml.etree (and to handle the CliXml format which is not
        standard XML).  The file is a PowerShell CliXml export; the ``Name``
        property appears as::

            <S N="Name">Microsoft.WinGet.Client</S>

        PSGetModuleInfo.xml files are saved in UTF-16 LE (Windows default for
        PowerShell Export-Clixml), so we try that encoding first then fall back
        to UTF-8.
        """
        import re

        name_re = re.compile(r'<S\s+N="Name">([^<]+)</S>', re.IGNORECASE)
        repo_re = re.compile(r'<S\s+N="Repository">([^<]+)</S>', re.IGNORECASE)
        for encoding in ("utf-16", "utf-8"):
            try:
                text = xml_path.read_text(encoding=encoding, errors="ignore")
                name_match = name_re.search(text)
                repo_match = repo_re.search(text)
                if not name_match:
                    continue
                repo = (repo_match.group(1) if repo_match else "").strip()
                if "psgallery" not in repo.lower():
                    return None
                return name_match.group(1).strip()
            except (OSError, UnicodeError):
                continue
        logging.debug(f"Could not read {xml_path}")
        return None
