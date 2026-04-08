"""Scan orchestrator.

:class:`Orchestrator` wires all pipeline stages in order:
prerequisites → WinGet/Scoop/registry/Chocolatey (parallel) → detector →
multi-manager search → cache → display → register.

The manager list is injected via the constructor so integration tests can
substitute mock adapters for the entire pipeline.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from wincoman.cache import default_cache_path, load_cache, save_cache
from wincoman.config import MANAGER_PREFERENCE, ScanConfig
from wincoman.detector import find_unmanaged
from wincoman.installer import register_interactive, register_packages
from wincoman.matchers.base import AppCandidates, InstallablePackageManager, PackageMatch, rank_candidates
from wincoman.matchers.chocolatey import ChocolateyManager
from wincoman.matchers.msstore import MicrosoftStoreManager
from wincoman.matchers.psgallery import PSGalleryManager
from wincoman.matchers.scoop import ScoopManager
from wincoman.matchers.winget import WinGetManager
from wincoman.registry import _FILTER_ALL, _FILTER_NO_MICROSOFT, _REGISTRY_QUERY_BASE, _deduplicate, scan_installed_programs
from wincoman.reporter import ScanSummary, display_results, display_summary, export_to_batch
from wincoman.shell import run_command

# Sentinel line that separates registry JSON from Microsoft Store output.
_SECTION_SEPARATOR = "---MSSTORE_SECTION---"

# Combined PowerShell script template: registry query + AppX query.
_COMBINED_PS_TEMPLATE = r"""
$UninstallKeys = @(
    "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
    "HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
    "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"
)
Get-ItemProperty $UninstallKeys -ErrorAction SilentlyContinue |
    Where-Object {{ {filter} }} |
    Select-Object DisplayName, DisplayVersion, Publisher |
    ConvertTo-Json -Compress

Write-Output '{separator}'

try {{
    Get-AppxPackage -PackageTypeFilter Main -ErrorAction Stop |
        Where-Object {{ $_.SignatureKind -eq 'Store' }} |
        ForEach-Object {{ $_.Name + '|' + $_.Version }}
}} catch {{
    Write-Output 'APPX_UNAVAILABLE'
}}
"""


def _run_combined_powershell(
    config: ScanConfig,
    msstore: MicrosoftStoreManager,
    *,
    runner=None,
) -> list[dict]:
    """Run registry scan + Microsoft Store query in **one** PowerShell process.

    Parses the combined output, feeds the AppX section directly into the
    :class:`MicrosoftStoreManager`'s internal cache so it does not need to
    spawn a second ``powershell.exe``.

    Returns the deduplicated registry program list.
    """
    if runner is None:
        runner = run_command

    where_filter = _FILTER_NO_MICROSOFT if config.exclude_microsoft else _FILTER_ALL
    ps_script = _COMBINED_PS_TEMPLATE.format(
        filter=where_filter,
        separator=_SECTION_SEPARATOR,
    )

    stdout, stderr, code = runner(["powershell", "-NoProfile", "-Command", ps_script], timeout=60)

    if code != 0:
        logging.error(f"Combined PowerShell query failed (exit {code}): {stderr}")
        return []

    # Split on the sentinel line.
    parts = stdout.split(_SECTION_SEPARATOR, 1)
    registry_raw = parts[0].strip() if len(parts) > 0 else ""
    msstore_raw = parts[1].strip() if len(parts) > 1 else ""

    # --- Parse registry section ---
    installed: list[dict] = []
    if registry_raw:
        try:
            programs = json.loads(registry_raw)
            if isinstance(programs, dict):
                programs = [programs]
            installed = _deduplicate(programs)
        except json.JSONDecodeError as exc:
            logging.error(f"Failed to parse installed programs: {exc}")

    if not installed:
        logging.error("No installed programs found — possible permission issue.")

    # --- Feed AppX section into MicrosoftStoreManager ---
    if msstore_raw and msstore_raw != "APPX_UNAVAILABLE":
        msstore._populate_from_raw(msstore_raw)
    elif msstore_raw == "APPX_UNAVAILABLE":
        msstore._available = False
        msstore._cache = {}

    return installed


class Orchestrator:
    """Wires all pipeline stages.  Manager list is constructor-injected."""

    def __init__(
        self,
        config: Optional[ScanConfig] = None,
        *,
        winget_mgr: Optional[WinGetManager] = None,
        scoop_mgr: Optional[ScoopManager] = None,
        choco_mgr: Optional[ChocolateyManager] = None,
        psgallery_mgr: Optional[PSGalleryManager] = None,
        msstore_mgr: Optional[MicrosoftStoreManager] = None,
    ) -> None:
        self.config = config or ScanConfig()
        self._winget = winget_mgr or WinGetManager(min_score=self.config.min_score)
        self._scoop = scoop_mgr or ScoopManager()
        self._choco = choco_mgr or ChocolateyManager(config=self.config)
        self._psgallery = psgallery_mgr or PSGalleryManager()
        self._msstore = msstore_mgr or MicrosoftStoreManager()
        # All managers that support install — ordered by MANAGER_PREFERENCE
        self._installable: list[InstallablePackageManager] = [self._winget, self._choco]

    def run(self) -> int:
        """Execute the full scan pipeline.

        Returns:
            Exit code: 0 on success, 1 on failure.
        """
        cfg = self.config
        summary = ScanSummary()

        logging.info("=" * 70)
        logging.info("  wincoman — Windows Computer Manager")
        logging.info("=" * 70)

        # ── Cache shortcut ────────────────────────────────────────────────────
        unmanaged_apps: list[dict] = []
        candidates: list[AppCandidates] = []

        if cfg.use_cache:
            cached = load_cache(cfg.cache_path)
            if cached is not None:
                unmanaged_apps, candidates = cached
            else:
                logging.warning("Cache unavailable — falling back to full scan.")
                cfg = ScanConfig(**{**cfg.__dict__, "use_cache": False})  # type: ignore[arg-type]

        if not cfg.use_cache:
            # Prerequisites
            if not self._check_prerequisites():
                return 1

            # ── Fan-out: run all independent queries concurrently ────────
            logging.info("\nSteps 1-3: Querying package managers & registry (parallel)")
            winget_ok, scoop_ok, choco_ok, installed = self._parallel_queries(cfg)

            if not winget_ok:
                logging.error("WinGet is not available.")
                return 1
            if not installed:
                logging.error("No installed programs found.")
                return 1
            if not choco_ok:
                logging.info("Chocolatey not available — skipping Chocolatey classification.")

            # Step 4: Detect unmanaged apps
            logging.info("\nStep 4/5: Classifying Installed Apps")
            managers = [self._winget, self._choco, self._scoop, self._psgallery, self._msstore]

            def _on_classify(app_name: str, manager_name: str | None) -> None:
                summary.record_classification(app_name, manager_name)
                max_w = 40
                app_display = (
                    (app_name[: max_w - 3] + "...") if len(app_name) > max_w else app_name
                )
                if manager_name:
                    logging.info(f"  {app_display:<42} managed by {manager_name}")
                else:
                    logging.info(f"  {app_display:<42} local only")

            unmanaged_apps = find_unmanaged(
                installed, managers, on_classify=_on_classify
            )
            logging.info(f"\nFound {len(unmanaged_apps)} unmanaged apps")

            if not unmanaged_apps:
                logging.info("All apps are already managed.")
                display_summary(summary)
                return 0

            # Step 5: Search all installable managers concurrently
            logging.info("\nStep 5/5: Searching Package Repositories")

            # Collect all matches keyed by app_name across managers
            all_results: dict[str, list[PackageMatch]] = {
                app["name"]: [] for app in unmanaged_apps
            }

            def _on_search_result(app_name: str, match: object | None) -> None:
                max_w = 40
                app_display = (
                    (app_name[: max_w - 3] + "...") if len(app_name) > max_w else app_name
                )
                if isinstance(match, PackageMatch):
                    all_results.setdefault(app_name, []).append(match)
                    pkg_info = f"{match.pkg_id} [{match.manager}] {match.pkg_version}"
                    mismatch_flag = " ⚠️ version mismatch" if match.version_mismatch else ""
                    logging.info(f"  {app_display:<42} found {pkg_info}{mismatch_flag}")

            for mgr in self._installable:
                if mgr.is_available():
                    logging.info(f"  Searching {mgr.name}...")
                    mgr.search_many(unmanaged_apps, on_result=_on_search_result)

            # After all managers searched — log apps with no match and tally stats
            for app in unmanaged_apps:
                app_name = app["name"]
                if all_results.get(app_name):
                    summary.record_search_result(app_name, all_results[app_name][0])
                else:
                    max_w = 40
                    app_display = (
                        (app_name[: max_w - 3] + "...") if len(app_name) > max_w else app_name
                    )
                    logging.info(f"  {app_display:<42} no match")
                    summary.record_search_result(app_name, None)

            candidates = rank_candidates(
                all_results,
                MANAGER_PREFERENCE,
                prefer_override=cfg.prefer_manager,
            )

            if not candidates:
                logging.warning("No matching packages found in any package manager.")
                display_summary(summary)
                return 0

            # Persist cache
            save_cache(cfg.cache_path, unmanaged_apps, candidates)

        if not candidates:
            logging.info("No unmanaged apps with package manager matches found.")
            return 0

        # Display
        display_summary(summary)
        display_results(candidates)

        if cfg.dry_run:
            logging.info("DRY-RUN: no packages were installed.")
            return 0

        # Build manager dispatch map
        mgr_map = {mgr.name: mgr for mgr in self._installable if mgr.is_available()}

        # Register
        if cfg.export_only:
            return 0 if export_to_batch(candidates, cfg.output_path) else 1

        # Admin check: only required when actually installing (not for scanning/export)
        if not self._check_install_privileges():
            logging.info("Re-run as Administrator to install packages.")
            return 0

        if cfg.auto:
            return 0 if register_packages(candidates, cfg, managers=mgr_map) else 1

        return 0 if register_interactive(candidates, cfg, managers=mgr_map) else 1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_prerequisites(self) -> bool:
        """Return True; prerequisites are now checked lazily (admin only at install time)."""
        return True

    def _check_install_privileges(self) -> bool:
        """Return True if running as Administrator (required for choco install)."""
        import sys

        if sys.platform == "win32":
            import ctypes

            if not ctypes.windll.shell32.IsUserAnAdmin():
                logging.warning(
                    "Not running as Administrator. "
                    "choco install requires elevation — install step will be skipped."
                )
                return False
        return True

    def _parallel_queries(
        self, cfg: ScanConfig
    ) -> tuple[bool, bool, bool, list[dict]]:
        """Run WinGet, Scoop, Chocolatey, PSGallery, and registry queries concurrently.

        Returns:
            ``(winget_ok, scoop_ok, choco_ok, installed_programs)``
        """

        def _winget_task() -> bool:
            if not self._winget.is_available():
                return False
            self._winget.list_managed()
            return True

        def _scoop_task() -> bool:
            if not self._scoop.is_available():
                return False
            self._scoop.list_managed()
            return True

        def _choco_task() -> bool:
            if not self._choco.is_available():
                return False
            self._choco.list_managed()
            return True

        def _psgallery_task() -> None:
            if self._psgallery.is_available():
                self._psgallery.list_managed()

        def _powershell_combined_task() -> list[dict]:
            """Run registry scan + Microsoft Store query in a single PowerShell process.

            This avoids spawning two separate powershell.exe processes, which
            reduces UAC/privilege-management prompts from corporate security
            tools (e.g. BeyondTrust) that intercept each powershell.exe launch.
            """
            return _run_combined_powershell(cfg, self._msstore)

        with ThreadPoolExecutor(max_workers=5) as pool:
            f_winget = pool.submit(_winget_task)
            f_scoop = pool.submit(_scoop_task)
            f_choco = pool.submit(_choco_task)
            pool.submit(_psgallery_task)
            f_combined = pool.submit(_powershell_combined_task)

            winget_ok = f_winget.result()
            scoop_ok = f_scoop.result()
            choco_ok = f_choco.result()
            installed = f_combined.result()

        return winget_ok, scoop_ok, choco_ok, installed
