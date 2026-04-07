"""Result display and batch-file export.

Functions here are pure output utilities — they need only the ``matches`` list
and never call subprocesses or interact with package managers.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Callable, Optional

from wincoman.matchers.base import PackageMatch


def display_results(matches: list[PackageMatch] | list[dict]) -> None:
    """Log a formatted table of *matches* to the root logger.

    Accepts either :class:`PackageMatch` instances or legacy ``dict`` entries
    (for backward compatibility with the old ``PackageManager.matches`` list).
    """
    logging.info("\n" + "=" * 70)
    logging.info("  RESULTS")
    logging.info("=" * 70)
    logging.info(f"\nFound {len(matches)} apps that can be registered with Chocolatey:\n")
    logging.info("-" * 70)
    logging.info(f"{'Installed App':<40} {'Chocolatey Package':<30}")
    logging.info("-" * 70)

    for match in matches:
        if isinstance(match, PackageMatch):
            app_name = match.app_name
            pkg_id = match.pkg_id
            mismatch = match.version_mismatch
        else:
            app_name = match.get("app_name", "")
            pkg_id = match.get("choco_id", "")
            mismatch = match.get("version_mismatch", False)

        max_width = 39
        app_display = (
            (app_name[: max_width - 3] + "...") if len(app_name) > max_width else app_name
        )
        mismatch_flag = " ⚠️ version mismatch" if mismatch else ""
        logging.info(f"{app_display:<40} {pkg_id:<30}{mismatch_flag}")

    logging.info("-" * 70)


def export_to_batch(
    matches: list[PackageMatch] | list[dict],
    output_path: Optional[str] = None,
    *,
    input_fn: Optional[Callable[[str], str]] = None,
) -> bool:
    """Write a ``choco install`` batch file for all *matches*.

    Args:
        matches: List of :class:`PackageMatch` or legacy dicts.
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
            fh.write("echo Registering unmanaged apps with Chocolatey...\r\n")
            fh.write("echo.\r\n")
            for match in matches:
                if isinstance(match, PackageMatch):
                    app_name = match.app_name
                    pkg_id = match.pkg_id
                else:
                    app_name = match.get("app_name", "")
                    pkg_id = match.get("choco_id", "")
                fh.write(f"echo Registering: {app_name}\r\n")
                fh.write(f"choco install {pkg_id} -y --force\r\n")
                fh.write("echo.\r\n")
            fh.write("echo.\r\n")
            fh.write("echo Registration complete!\r\n")
            fh.write("pause\r\n")

        logging.info(f"Batch file saved: {output_path}")
        return True
    except OSError as exc:
        logging.error(f"Failed to create batch file: {exc}")
        return False
