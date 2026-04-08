"""WinGet package manager adapter.

Implements :class:`InstallablePackageManager` for WinGet (Windows Package Manager).
Supports both detection (``winget list``) and search/install
(``winget search`` / ``winget install``).
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from rapidfuzz import fuzz, process

from wincoman.matchers.base import InstallablePackageManager, PackageMatch
from wincoman.scoring import normalize_name, strip_version_suffix, versions_differ
from wincoman.shell import run_command

_DEFAULT_MIN_SCORE = 60


class WinGetManager(InstallablePackageManager):
    """Adapter for the Windows Package Manager (winget)."""

    def __init__(
        self,
        min_score: int = _DEFAULT_MIN_SCORE,
        runner: Optional[Callable] = None,
        search_workers: int = 5,
    ) -> None:
        self._min_score = min_score
        self._runner = runner or run_command
        self._search_workers = search_workers
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
        # Also try with version suffix stripped (e.g. "HWiNFO64 7.28" → "HWiNFO64")
        stripped_lower = strip_version_suffix(display_name).lower()
        if stripped_lower != name_lower and stripped_lower in name_map:
            return True
        if not name_map:
            return False
        # Fuzzy fallback — query with version stripped for better accuracy
        query = strip_version_suffix(display_name)
        result = process.extractOne(
            query,
            name_map.keys(),
            scorer=fuzz.WRatio,
            score_cutoff=self._min_score,
        )
        return result is not None

    def search(self, app_name: str) -> Optional[PackageMatch]:
        """Search the WinGet repository for *app_name*.

        Runs ``winget search --query <name> --output json`` and returns the
        best fuzzy match above the configured threshold, or ``None``.

        Version suffixes are stripped from *app_name* before querying so that
        display names like ``"HWiNFO64 7.28-4900"`` resolve correctly.
        """
        query = strip_version_suffix(app_name)
        stdout, _, code = self._runner(
            [
                "winget", "search",
                "--query", query,
                "--output", "json",
                "--accept-source-agreements",
            ]
        )
        if code != 0 or not stdout.strip():
            return None

        try:
            results = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(results, list) or not results:
            return None

        # Score every candidate against both the original and stripped name;
        # pick the best above threshold.
        best_match: Optional[PackageMatch] = None
        best_score = 0
        for pkg in results:
            candidate_name = (pkg.get("Name") or "").strip()
            candidate_id = (pkg.get("Id") or "").strip()
            candidate_ver = (pkg.get("Version") or "").strip()
            if not candidate_id:
                continue
            # Score against both the stripped query and the original name
            score_name = max(fuzz.WRatio(query, candidate_name),
                             fuzz.WRatio(app_name, candidate_name))
            score_id   = max(fuzz.WRatio(query, candidate_id),
                             fuzz.WRatio(app_name, candidate_id))
            score = max(score_name, score_id)
            if score > best_score:
                best_score = score
                best_match = PackageMatch(
                    app_name=app_name,
                    app_version="",
                    pkg_id=candidate_id,
                    pkg_version=candidate_ver,
                    version_mismatch=False,
                    manager=self.name,
                )

        if best_score >= self._min_score and best_match is not None:
            return best_match
        return None

    def search_many(
        self,
        apps: list[dict],
        *,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        on_result: Optional[Callable[[str, Optional[PackageMatch]], None]] = None,
    ) -> list[PackageMatch]:
        """Search the WinGet repository for all apps concurrently."""
        total = len(apps)
        workers = min(self._search_workers, total) if total else 1
        results: list[PackageMatch] = []
        completed = 0

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_app = {
                pool.submit(self.search, app["name"]): app for app in apps
            }
            for future in as_completed(future_to_app):
                completed += 1
                if progress_cb:
                    progress_cb(completed, total)
                app = future_to_app[future]
                match = future.result()
                enriched: Optional[PackageMatch] = None
                if match is not None:
                    app_ver = app.get("version", "")
                    mismatch = versions_differ(app_ver, match.pkg_version)
                    enriched = PackageMatch(
                        app_name=app["name"],
                        app_version=app_ver,
                        pkg_id=match.pkg_id,
                        pkg_version=match.pkg_version,
                        version_mismatch=mismatch,
                        manager=self.name,
                    )
                    results.append(enriched)
                if on_result is not None:
                    on_result(app["name"], enriched)
        return results

    def install(self, match: PackageMatch, *, dry_run: bool = False) -> bool:
        """Install *match* via ``winget install``.

        Returns ``True`` on success or dry-run, ``False`` on failure.
        """
        cmd = [
            "winget", "install",
            "--id", match.pkg_id,
            "--exact",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
        if dry_run:
            logging.info(f"    [DRY-RUN] Would run: {' '.join(cmd)}")
            return True
        _, stderr, code = self._runner(cmd)
        if code != 0:
            logging.error(f"    winget install failed: {stderr[:200]}")
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_name_map(self) -> dict[str, str]:
        """Return a cached ``{name_lower: id}`` map from winget list.

        Tries ``winget list --output json`` first (winget ≥ 1.5+).
        If that fails (older winget or missing flag), falls back to parsing
        the plain tabular output of ``winget list``.

        Both the original name AND the version-stripped name are indexed so
        that ``is_managed()`` can look up entries regardless of whether the
        name_map or the registry DisplayName carries the version.
        """
        if self._cache is not None:
            return self._cache

        packages = self._fetch_packages_json()
        if packages is None:
            packages = self._fetch_packages_table()

        result: dict[str, str] = {}
        for pkg in packages:
            name = (pkg.get("Name") or "").strip()
            pkg_id = pkg.get("Id", "")
            if not name:
                continue
            name_lower = name.lower()
            result[name_lower] = pkg_id
            # Also index by version-stripped name so we match entries like
            # "7-Zip 26.00 (x64)" → "7-zip" without needing exact version.
            stripped = strip_version_suffix(name).lower()
            if stripped and stripped != name_lower:
                result.setdefault(stripped, pkg_id)
            # Normalized form (no special chars) for apps like "draw.io" → "drawio"
            norm = normalize_name(name)
            if norm and norm != name_lower:
                result.setdefault(norm, pkg_id)

        self._cache = result
        return self._cache

    def _fetch_packages_json(self) -> Optional[list[dict]]:
        """Try ``winget list --output json``; return package list or None."""
        stdout, _, code = self._runner(
            ["winget", "list", "--output", "json", "--accept-source-agreements"]
        )
        if code != 0 or not stdout.strip():
            return None
        try:
            data = json.loads(stdout)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _fetch_packages_table(self) -> list[dict]:
        """Parse ``winget list`` tabular output into a list of dicts.

        Handles the plain text table that older winget versions produce when
        ``--output json`` is not recognised.  Column boundaries are inferred
        from the header line (the line containing 'Name' and 'Id').
        """
        stdout, stderr, code = self._runner(
            ["winget", "list", "--accept-source-agreements"]
        )
        if code != 0 or not stdout.strip():
            logging.warning(f"winget list failed: {stderr}")
            return []
        return _parse_winget_table(stdout)


def _parse_winget_table(text: str) -> list[dict]:
    """Parse winget plain-text tabular output into ``[{Name, Id}, ...]``.

    Finds the header row by locating the line that contains both ``Name``
    and ``Id``, then uses character positions to slice each data row.

    Robust against:
    * Leading spinner/progress lines (``- ``)
    * A single long separator line (``---...``)
    * Names that include version numbers (e.g. ``draw.io 29.6.6``)
    """
    lines = text.splitlines()

    # Locate the header line
    header_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if "Name" in line and "Id" in line:
            header_idx = i
            break
    if header_idx is None:
        return []

    header = lines[header_idx]
    name_col = header.index("Name")
    id_col = header.index("Id")
    # Version column optional
    ver_col: Optional[int] = header.find("Version")
    if ver_col == -1:
        ver_col = None

    packages: list[dict] = []
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        # Skip blank lines and the separator (all dashes / spaces)
        if not stripped or all(c in "- " for c in stripped):
            continue
        if len(line) <= name_col:
            continue

        name = line[name_col:id_col].strip() if len(line) > id_col else line[name_col:].strip()
        id_part = line[id_col:ver_col].strip() if ver_col and len(line) > id_col else (
            line[id_col:].split()[0] if len(line) > id_col else ""
        )
        if name:
            packages.append({"Name": name, "Id": id_part})

    return packages
