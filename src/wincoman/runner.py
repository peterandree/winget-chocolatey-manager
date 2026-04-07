"""Scan orchestrator.

:class:`Orchestrator` wires all pipeline stages in order:
prerequisites → WinGet → Scoop → registry → Chocolatey list → detector →
Chocolatey search → cache → display → register.

The manager list is injected via the constructor so integration tests can
substitute mock adapters for the entire pipeline.
"""
from __future__ import annotations

import logging
from typing import Optional

from wincoman.cache import default_cache_path, load_cache, save_cache
from wincoman.config import ScanConfig
from wincoman.detector import find_unmanaged
from wincoman.installer import register_interactive, register_packages
from wincoman.matchers.chocolatey import ChocolateyManager
from wincoman.matchers.scoop import ScoopManager
from wincoman.matchers.winget import WinGetManager
from wincoman.registry import scan_installed_programs
from wincoman.reporter import display_results, export_to_batch


class Orchestrator:
    """Wires all pipeline stages.  Manager list is constructor-injected."""

    def __init__(
        self,
        config: Optional[ScanConfig] = None,
        *,
        winget_mgr: Optional[WinGetManager] = None,
        scoop_mgr: Optional[ScoopManager] = None,
        choco_mgr: Optional[ChocolateyManager] = None,
    ) -> None:
        self.config = config or ScanConfig()
        self._winget = winget_mgr or WinGetManager(min_score=self.config.min_score)
        self._scoop = scoop_mgr or ScoopManager()
        self._choco = choco_mgr or ChocolateyManager(config=self.config)

    def run(self) -> int:
        """Execute the full scan pipeline.

        Returns:
            Exit code: 0 on success, 1 on failure.
        """
        cfg = self.config

        logging.info("=" * 70)
        logging.info("  wincoman — Windows Computer Manager")
        logging.info("=" * 70)

        # ── Cache shortcut ────────────────────────────────────────────────────
        unmanaged_apps: list[dict] = []
        matches: list = []

        if cfg.use_cache:
            cached = load_cache(cfg.cache_path)
            if cached is not None:
                unmanaged_apps, matches = cached
            else:
                logging.warning("Cache unavailable — falling back to full scan.")
                cfg = ScanConfig(**{**cfg.__dict__, "use_cache": False})  # type: ignore[arg-type]

        if not cfg.use_cache:
            # Prerequisites
            if not self._check_prerequisites():
                return 1

            # Step 1: WinGet packages (populates WinGetManager cache)
            logging.info("\nStep 1/5: Checking WinGet Managed Packages")
            if not self._winget.is_available():
                logging.error("WinGet is not available.")
                return 1
            self._winget.list_managed()  # prime cache

            # Step 1b: Scoop (optional)
            if self._scoop.is_available():
                self._scoop.list_managed()

            # Step 2: Registry scan
            logging.info("\nStep 2/5: Scanning Installed Programs")
            installed = scan_installed_programs(cfg)
            if not installed:
                logging.error("No installed programs found.")
                return 1

            # Step 3: Chocolatey list
            logging.info("\nStep 3/5: Checking Chocolatey Packages")
            if not self._choco.is_available():
                logging.error("Chocolatey is not available.")
                return 1
            self._choco.list_managed()  # prime cache

            # Step 4: Detect unmanaged apps
            logging.info("\nStep 4/5: Finding Unmanaged Apps")
            managers = [self._winget, self._choco, self._scoop]
            unmanaged_apps = find_unmanaged(installed, managers)
            logging.info(f"Found {len(unmanaged_apps)} unmanaged apps")

            if not unmanaged_apps:
                logging.info("All apps are already managed.")
                return 0

            # Step 5: Search Chocolatey repository
            logging.info("\nStep 5/5: Searching Chocolatey Repository")

            def _progress(i: int, total: int) -> None:
                if i % 5 == 0 or i == total:
                    logging.info(f"Progress: {i}/{total} apps processed...")

            matches = self._choco.search_many(unmanaged_apps, progress_cb=_progress)

            if not matches:
                logging.warning("No matching Chocolatey packages found.")
                return 0

            # Persist cache
            save_cache(cfg.cache_path, unmanaged_apps, matches)

        if not matches:
            logging.info("No unmanaged apps with Chocolatey matches found.")
            return 0

        # Display
        display_results(matches)

        if cfg.dry_run:
            logging.info("DRY-RUN: no packages were installed.")
            return 0

        # Register
        if cfg.export_only:
            return 0 if export_to_batch(matches, cfg.output_path) else 1

        if cfg.auto:
            return 0 if register_packages(matches, cfg) else 1

        return 0 if register_interactive(matches, cfg) else 1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_prerequisites(self) -> bool:
        """Check admin privileges (required for choco install)."""
        import sys

        if sys.platform == "win32":
            import ctypes

            if not ctypes.windll.shell32.IsUserAnAdmin():
                logging.error(
                    "Not running as Administrator. "
                    "choco install requires elevation."
                )
                return False
        return True
