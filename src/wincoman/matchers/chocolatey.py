"""Chocolatey package manager adapter.

Implements :class:`SearchablePackageManager` for Chocolatey.  This is the most
complex adapter as it both lists locally-installed packages and searches the
Chocolatey community repository.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from wincoman.config import ScanConfig
from wincoman.matchers.base import InstallablePackageManager, PackageMatch
from wincoman.scoring import fuzzy_score, normalize_name, strip_version_suffix, versions_differ
from wincoman.shell import run_command


class ChocolateyManager(InstallablePackageManager):
    """Adapter for Chocolatey (choco)."""

    def __init__(
        self,
        config: Optional[ScanConfig] = None,
        runner: Optional[Callable] = None,
        sleep: Optional[Callable] = None,
    ) -> None:
        self._config = config or ScanConfig()
        self._runner = runner or run_command
        self._sleep = sleep or time.sleep
        self._cache: Optional[set[str]] = None
        self._available: Optional[bool] = None

    @property
    def name(self) -> str:
        return "chocolatey"

    def is_available(self) -> bool:
        """Return True when choco is on PATH and responds."""
        if self._available is None:
            _, _, code = self._runner(["choco", "--version"])
            self._available = code == 0
        return self._available

    def list_managed(self) -> set[str]:
        """Return normalised names of all locally-installed Chocolatey packages."""
        return self._get_package_set()

    def is_managed(self, display_name: str) -> bool:
        """Return True if *display_name* matches a locally-installed Chocolatey package.

        Tries multiple key forms:
        1. Normalised full display name
        2. Version-stripped normalised
        3. Version-stripped lowercase
        4. Prefix match — choco package name is a prefix of the normalised name
           (e.g. choco ``filezilla`` matches registry ``FileZilla Client``)
        """
        packages = self._get_package_set()
        # 1. Full normalised
        norm = normalize_name(display_name)
        if norm in packages:
            return True
        # 2. Version-stripped normalised
        stripped = strip_version_suffix(display_name)
        stripped_norm = normalize_name(stripped)
        if stripped_norm and stripped_norm != norm and stripped_norm in packages:
            return True
        # 3. Exact lowercase of stripped name
        stripped_lower = stripped.lower()
        if stripped_lower in packages:
            return True
        # 4. Prefix match: check if the choco package name starts with the
        #    normalised display name or vice versa (e.g. choco ``filezilla``
        #    matches ``filezillaclient``; choco ``autohotkeyportable`` matches
        #    display ``autohotkey``).  Only match if the shorter string is ≥4
        #    chars to avoid false positives.
        target = stripped_norm or norm
        if target and len(target) >= 4:
            for pkg in packages:
                if len(pkg) < 4:
                    continue
                if target.startswith(pkg) or pkg.startswith(target):
                    return True
        return False

    def search(self, app_name: str) -> Optional[PackageMatch]:
        """Search the Chocolatey repository for *app_name*.

        Tries an exact search first, then falls back to fuzzy scoring.
        Version suffixes are stripped before querying so that display names
        like ``"HWiNFO64 7.28-4900"`` resolve correctly.
        Returns ``None`` if no candidate meets the configured score threshold.
        """
        limit_flag = self._limit_output_flag()
        query = strip_version_suffix(app_name)

        # Exact search (using stripped query)
        stdout, _, code = self._runner(
            ["choco", "search", query, "--exact"] + limit_flag
        )
        if code == 0 and stdout.strip():
            parts = stdout.strip().split("\n")[0].split("|")
            if len(parts) >= 2:
                pkg_id, pkg_ver = parts[0].strip(), parts[1].strip()
                return PackageMatch(
                    app_name=app_name,
                    app_version="",
                    pkg_id=pkg_id,
                    pkg_version=pkg_ver,
                    version_mismatch=False,
                    manager=self.name,
                )

        # Fuzzy search (using stripped query; score against both forms)
        stdout, _, code = self._runner(["choco", "search", query] + limit_flag)
        if code == 0 and stdout.strip():
            best_id: Optional[str] = None
            best_ver: Optional[str] = None
            best_score = 0
            for line in stdout.strip().split("\n"):
                parts = line.split("|")
                if len(parts) >= 2:
                    candidate_id = parts[0].strip()
                    score = max(
                        fuzzy_score(query, candidate_id),
                        fuzzy_score(app_name, candidate_id),
                    )
                    if score > best_score:
                        best_score = score
                        best_id = candidate_id
                        best_ver = parts[1].strip()
            if best_score >= self._config.min_score and best_id is not None:
                return PackageMatch(
                    app_name=app_name,
                    app_version="",
                    pkg_id=best_id,
                    pkg_version=best_ver or "",
                    version_mismatch=False,
                    manager=self.name,
                )

        return None

    def search_many(
        self,
        apps: list[dict],
        *,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        on_result: Optional[Callable[[str, Optional[PackageMatch]], None]] = None,
    ) -> list[PackageMatch]:
        """Search the repository for all apps in *apps* concurrently.

        Each element of *apps* must have at least a ``'name'`` key.
        Uses a thread pool sized by ``ScanConfig.search_workers``.
        """
        total = len(apps)
        workers = min(self._config.search_workers, total) if total else 1
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
        """Install *match* via ``choco install``.

        Returns ``True`` on success or dry-run, ``False`` on failure.
        """
        cmd = ["choco", "install", match.pkg_id, "-y", "--force"]
        if dry_run:
            logging.info(f"    [DRY-RUN] Would run: {' '.join(cmd)}")
            return True
        _, stderr, code = self._runner(cmd)
        if code != 0:
            logging.error(f"    choco install failed: {stderr[:200]}")
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_package_set(self) -> set[str]:
        if self._cache is not None:
            return self._cache

        # --limit-output produces consistent "name|version" output in both
        # choco v1 and v2 (deprecated in v2 but still supported).  The default
        # v2 output is human-readable space-separated text which is harder to
        # parse reliably, so we always request machine-readable pipe format.
        stdout, stderr, code = self._runner(["choco", "list", "--limit-output"])

        if code != 0:
            logging.warning(f"choco list failed: {stderr}")
            self._cache = set()
            return self._cache

        packages: set[str] = set()
        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 2:
                raw = parts[0].strip()
                norm = normalize_name(raw)
                if norm:
                    packages.add(norm)
                # Also add the raw lowercase name for exact matching
                # (e.g. "filezilla" as-is, not just "filezilla" normalised)
                if raw:
                    packages.add(raw.lower())
        self._cache = packages
        return self._cache

    def _limit_output_flag(self) -> list[str]:
        # Always use --limit-output for consistent pipe-separated output
        return ["--limit-output"]
