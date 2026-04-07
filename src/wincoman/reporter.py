"""Result display and batch-file export.

Functions here are pure output utilities — they need only the ``matches`` list
and never call subprocesses or interact with package managers.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from wincoman.matchers.base import AppCandidates, PackageMatch


@dataclass
class ScanSummary:
    """Accumulated statistics for a single scan run."""

    total_scanned: int = 0
    managed_by: dict[str, int] = field(default_factory=dict)
    local_only: int = 0
    search_matches_found: int = 0
    search_no_match: int = 0

    def record_classification(
        self, app_name: str, manager_name: Optional[str]
    ) -> None:
        """Record a single app's classification from the detector callback."""
        self.total_scanned += 1
        if manager_name:
            self.managed_by[manager_name] = self.managed_by.get(manager_name, 0) + 1
        else:
            self.local_only += 1

    def record_search_result(
        self, app_name: str, match: Optional[PackageMatch]
    ) -> None:
        """Record a single package-manager search result."""
        if match is not None:
            self.search_matches_found += 1
        else:
            self.search_no_match += 1

    # Legacy aliases kept for backwards-compat with existing tests
    @property
    def choco_matches_found(self) -> int:
        return self.search_matches_found

    @choco_matches_found.setter
    def choco_matches_found(self, v: int) -> None:
        self.search_matches_found = v

    @property
    def choco_no_match(self) -> int:
        return self.search_no_match

    @choco_no_match.setter
    def choco_no_match(self, v: int) -> None:
        self.search_no_match = v


def display_summary(summary: ScanSummary) -> None:
    """Log a formatted scan summary block."""
    logging.info("\n" + "=" * 70)
    logging.info("  SCAN SUMMARY")
    logging.info("=" * 70)
    logging.info(f"  Total installed programs scanned:   {summary.total_scanned:>5}")
    for mgr_name, count in sorted(summary.managed_by.items()):
        logging.info(f"  Managed by {mgr_name + ':':<28} {count:>5}")
    logging.info(f"  Local only (unmanaged):             {summary.local_only:>5}")
    if summary.search_matches_found or summary.search_no_match:
        logging.info("  " + "-" * 40)
        logging.info(f"  Package manager matches found:      {summary.search_matches_found:>5}")
        logging.info(f"  No package manager match:           {summary.search_no_match:>5}")
    logging.info("=" * 70)


def display_results(matches: list[AppCandidates] | list[PackageMatch] | list[dict]) -> None:
    """Log a formatted table of *matches* to the root logger.

    Accepts :class:`AppCandidates`, :class:`PackageMatch` instances, or legacy
    ``dict`` entries (for backward compatibility).
    """
    logging.info("\n" + "=" * 70)
    logging.info("  RESULTS")
    logging.info("=" * 70)
    logging.info(f"\nFound {len(matches)} apps that can be registered:\n")
    logging.info("-" * 70)
    logging.info(f"{'Installed App':<40} {'Package / Manager':<30}")
    logging.info("-" * 70)

    for entry in matches:
        if isinstance(entry, AppCandidates):
            app_name = entry.app_name
            pkg_id = entry.primary.pkg_id
            manager = entry.primary.manager
            mismatch = entry.primary.version_mismatch
            alt_count = len(entry.alternatives)
            alt_suffix = f" (+{alt_count} alt)" if alt_count else ""
            pkg_display = f"{pkg_id} [{manager}]{alt_suffix}"
        elif isinstance(entry, PackageMatch):
            app_name = entry.app_name
            pkg_display = f"{entry.pkg_id} [{entry.manager}]"
            mismatch = entry.version_mismatch
        else:
            app_name = entry.get("app_name", "")
            choco_id = entry.get("choco_id", "")
            pkg_display = f"{choco_id} [chocolatey]"
            mismatch = entry.get("version_mismatch", False)

        max_width = 39
        app_display = (
            (app_name[: max_width - 3] + "...") if len(app_name) > max_width else app_name
        )
        mismatch_flag = " ⚠️ version mismatch" if mismatch else ""
        logging.info(f"{app_display:<40} {pkg_display:<30}{mismatch_flag}")

    logging.info("-" * 70)


def install_command(match: PackageMatch) -> str:
    """Return the shell command string that would install *match*."""
    if match.manager == "winget":
        return (
            f"winget install --id {match.pkg_id} --exact --silent"
            " --accept-package-agreements --accept-source-agreements"
        )
    if match.manager == "chocolatey":
        return f"choco install {match.pkg_id} -y --force"
    if match.manager == "scoop":
        return f"scoop install {match.pkg_id}"
    # Generic fallback
    return f"# install {match.pkg_id} via {match.manager}"


def export_to_batch(
    matches: list[AppCandidates] | list[PackageMatch] | list[dict],
    output_path: Optional[str] = None,
    *,
    input_fn: Optional[Callable[[str], str]] = None,
) -> bool:
    """Write an install batch file for all *matches*.

    Args:
        matches: List of :class:`AppCandidates`, :class:`PackageMatch`, or
            legacy dicts.
        output_path: Destination path.  Defaults to a timestamped filename in
            the current directory.
        input_fn: Injectable input function (default: built-in ``input``).
            Swap out in tests to avoid blocking on stdin.

    Returns:
        ``True`` on success, ``False`` if the user cancelled or write failed.
    """
    if input_fn is None:
        input_fn = input  # resolved at call time so patch('builtins.input') works
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"register_unmanaged_apps_{timestamp}.bat"

    if os.path.exists(output_path):
        while True:
            response = input_fn(
                f"\n'{output_path}' already exists. Overwrite? (y/n): "
            ).strip().lower()
            if response in ("y", "n"):
                break
        if response != "y":
            logging.info("Export cancelled.")
            return False

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write("@echo off\r\n")
            fh.write("echo Registering unmanaged apps...\r\n")
            fh.write("echo.\r\n")
            for entry in matches:
                if isinstance(entry, AppCandidates):
                    app_name = entry.app_name
                    cmd_str = install_command(entry.primary)
                elif isinstance(entry, PackageMatch):
                    app_name = entry.app_name
                    cmd_str = install_command(entry)
                else:
                    app_name = entry.get("app_name", "")
                    pkg_id = entry.get("choco_id", "")
                    cmd_str = f"choco install {pkg_id} -y --force"
                fh.write(f"echo Registering: {app_name}\r\n")
                fh.write(f"{cmd_str}\r\n")
                fh.write("echo.\r\n")
            fh.write("echo.\r\n")
            fh.write("echo Registration complete!\r\n")
            fh.write("pause\r\n")

        logging.info(f"Batch file saved: {output_path}")
        return True
    except OSError as exc:
        logging.error(f"Failed to create batch file: {exc}")
        return False
