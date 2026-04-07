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
from wincoman.matchers.base import PackageMatch, SearchablePackageManager
from wincoman.scoring import fuzzy_score, normalize_name, versions_differ
from wincoman.shell import get_choco_major_version, run_command


class ChocolateyManager(SearchablePackageManager):
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
        self._choco_ver: Optional[int] = None
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
        """Return True if *display_name* matches a locally-installed Chocolatey package."""
        return normalize_name(display_name) in self._get_package_set()

    def search(self, app_name: str) -> Optional[PackageMatch]:
        """Search the Chocolatey repository for *app_name*.

        Tries an exact search first, then falls back to fuzzy scoring.
        Returns ``None`` if no candidate meets the configured score threshold.
        """
        limit_flag = self._limit_output_flag()

        # Exact search
        stdout, _, code = self._runner(
            ["choco", "search", app_name, "--exact"] + limit_flag
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

        # Fuzzy search
        stdout, _, code = self._runner(["choco", "search", app_name] + limit_flag)
        if code == 0 and stdout.strip():
            best_id: Optional[str] = None
            best_ver: Optional[str] = None
            best_score = 0
            for line in stdout.strip().split("\n"):
                parts = line.split("|")
                if len(parts) >= 2:
                    candidate_id = parts[0].strip()
                    score = fuzzy_score(app_name, candidate_id)
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
                if match is not None:
                    app_ver = app.get("version", "")
                    mismatch = versions_differ(app_ver, match.pkg_version)
                    results.append(
                        PackageMatch(
                            app_name=app["name"],
                            app_version=app_ver,
                            pkg_id=match.pkg_id,
                            pkg_version=match.pkg_version,
                            version_mismatch=mismatch,
                            manager=self.name,
                        )
                    )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_package_set(self) -> set[str]:
        if self._cache is not None:
            return self._cache

        choco_major = self._choco_major_version()
        cmd = ["choco", "list"] if choco_major >= 2 else ["choco", "list", "--limit-output"]
        stdout, stderr, code = self._runner(cmd)

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
                norm = normalize_name(parts[0])
                if norm:
                    packages.add(norm)
        self._cache = packages
        return self._cache

    def _limit_output_flag(self) -> list[str]:
        return [] if self._choco_major_version() >= 2 else ["--limit-output"]

    def _choco_major_version(self) -> int:
        if self._choco_ver is None:
            self._choco_ver = get_choco_major_version(runner=self._runner)
        return self._choco_ver
