"""Microsoft Store (AppX / MSIX) package manager adapter.

Detects UWP / MSIX apps installed via the Microsoft Store by calling
``Get-AppxPackage`` through PowerShell.  This is a read-only adapter —
it classifies apps as Store-managed but does not install or uninstall.

The adapter indexes both the raw AppX package name (e.g.
``Microsoft.WindowsCalculator``) and common normalised forms so that
registry ``DisplayName`` values like ``"Windows Calculator"`` are matched.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from wincoman.matchers.base import BasePackageManager
from wincoman.scoring import normalize_name
from wincoman.shell import run_command


class MicrosoftStoreManager(BasePackageManager):
    """Adapter for Microsoft Store apps (Get-AppxPackage)."""

    def __init__(self, runner: Optional[Callable] = None) -> None:
        self._runner = runner or run_command
        self._cache: Optional[dict[str, str]] = None  # normalized -> raw name
        self._available: Optional[bool] = None

    # Well-known AppX-to-display-name aliases for packages where the AppX name
    # does not match the user-visible name at all.
    _DISPLAY_ALIASES: dict[str, list[str]] = {
        "microsoft.screensketch": ["snipping tool"],
        "microsoft.yourphone": ["phone link"],
        "microsoft.windowsstore": ["microsoft store"],
        "microsoft.windows.photos": ["microsoft photos"],
        "microsoft.windowscamera": ["windows camera"],
        "microsoft.windowsalarms": ["windows clock"],
        "microsoft.windowsfeedbackhub": ["feedback hub"],
        "microsoft.windowscalculator": ["windows calculator"],
        "microsoft.windowsnotepad": ["windows notepad"],
        "microsoft.powerautomatedesktop": ["power automate"],
        "microsoft.desktopappinstaller": ["app installer"],
        "microsoft.paint": ["paint"],
        "microsoft.securityhealthui": ["windows security"],
        "microsoft.securehealthui": ["windows security"],
        "microsoft.sechealthui": ["windows security"],
        "microsoft.gethelpx": ["get help"],
        "microsoft.gethelp": ["get help"],
        "microsoft.officehub": ["microsoft 365 copilot"],
        "microsoft.microsoftofficehub": ["microsoft 365 copilot"],
        "microsoftwindows.client.webexperience": ["windows web experience pack"],
        "microsoftwindows.crossdevice": ["cross device experience host"],
        "microsoftcorporationii.windows365": ["windows app"],
    }

    @property
    def name(self) -> str:
        return "msstore"

    def is_available(self) -> bool:
        """Return True when PowerShell + Get-AppxPackage works."""
        if self._available is None:
            _, _, code = self._runner(
                ["powershell", "-NoProfile", "-Command",
                 "Get-AppxPackage -PackageTypeFilter Main | Select-Object -First 1 Name"],
                timeout=15,
            )
            self._available = code == 0
        return self._available

    def list_managed(self) -> set[str]:
        """Return normalised names of all Store-installed apps."""
        return set(self._get_name_map().keys())

    def is_managed(self, display_name: str) -> bool:
        """Return True if *display_name* matches a Store-installed app."""
        name_map = self._get_name_map()

        # Exact lowercase
        lower = display_name.lower()
        if lower in name_map:
            return True

        # Normalised (alphanumeric only)
        norm = normalize_name(display_name)
        if norm in name_map:
            return True

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_name_map(self) -> dict[str, str]:
        """Return ``{normalised_key: appx_name}`` for all Store apps.

        Indexes every app under multiple key forms:
        - Raw AppX name lowercase (``microsoft.windowscalculator``)
        - Normalised AppX name (``microsoftwindowscalculator``)
        - Friendly suffix: last dotted segment (``windowscalculator``)
        - Friendly suffix without vendor (``calculator``) for common Microsoft prefix
        """
        if self._cache is not None:
            return self._cache

        stdout, stderr, code = self._runner(
            ["powershell", "-NoProfile", "-Command",
             "Get-AppxPackage -PackageTypeFilter Main "
             "| Where-Object { $_.SignatureKind -eq 'Store' } "
             "| ForEach-Object { $_.Name + '|' + $_.Version }"],
            timeout=30,
        )

        result: dict[str, str] = {}
        if code != 0:
            logging.info("Get-AppxPackage unavailable — skipping Microsoft Store detection.")
            self._cache = result
            return result

        for line in stdout.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|", 1)
            raw_name = parts[0].strip()
            if not raw_name:
                continue

            # Index under multiple forms for matching
            lower = raw_name.lower()
            result[lower] = raw_name

            norm = normalize_name(raw_name)
            if norm:
                result.setdefault(norm, raw_name)

            # Last segment after the last dot — e.g. "WindowsCalculator"
            if "." in raw_name:
                suffix = raw_name.rsplit(".", 1)[-1]
                suffix_lower = suffix.lower()
                if suffix_lower and len(suffix_lower) > 2:
                    result.setdefault(suffix_lower, raw_name)
                    suffix_norm = normalize_name(suffix)
                    if suffix_norm and suffix_norm != suffix_lower:
                        result.setdefault(suffix_norm, raw_name)

            # Handle common vendor prefixes:
            # "Microsoft.WindowsCalculator" → "windows calculator" → "windowscalculator"
            # "Microsoft.GetHelp" → "get help" → "gethelp"
            for prefix in ("microsoft.", "microsoftcorporationii.", "microsoftwindows."):
                if lower.startswith(prefix):
                    stripped = lower[len(prefix):]
                    if stripped and len(stripped) > 2:
                        result.setdefault(stripped, raw_name)
                        stripped_norm = normalize_name(stripped)
                        if stripped_norm:
                            result.setdefault(stripped_norm, raw_name)

            # Well-known display name aliases
            for alias in self._DISPLAY_ALIASES.get(lower, []):
                result.setdefault(alias.lower(), raw_name)
                alias_norm = normalize_name(alias)
                if alias_norm:
                    result.setdefault(alias_norm, raw_name)

        self._cache = result
        if result:
            unique = len({v for v in result.values()})
            logging.info(f"Found {unique} Microsoft Store apps")
        return self._cache
