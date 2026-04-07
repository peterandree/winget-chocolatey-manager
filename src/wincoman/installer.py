"""Package registration — choco install execution.

:func:`register_packages` runs ``choco install`` for each package in the
provided list.  :func:`register_interactive` wraps it with a user-facing menu.
Both functions are stateless — they receive data rather than reading from a
``PackageManager`` instance.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from wincoman.config import ScanConfig
from wincoman.matchers.base import PackageMatch
from wincoman.reporter import export_to_batch
from wincoman.shell import run_command


def register_packages(
    packages: list[PackageMatch] | list[dict],
    config: Optional[ScanConfig] = None,
    *,
    runner: Optional[Callable] = None,
) -> bool:
    """Execute ``choco install`` for each package.

    Respects ``config.dry_run`` — in dry-run mode no install commands are run.

    Returns:
        ``True`` if all registrations succeeded, ``False`` if any failed.
    """
    if config is None:
        config = ScanConfig()
    if runner is None:
        runner = run_command

    logging.info(f"\n{'='*70}")
    logging.info(f"  Registering {len(packages)} Package(s)")
    logging.info("=" * 70)

    successful = []
    failed = []

    for i, match in enumerate(packages, 1):
        if isinstance(match, PackageMatch):
            app_name = match.app_name
            pkg_id = match.pkg_id
        else:
            app_name = match.get("app_name", "")
            pkg_id = match.get("choco_id", "")

        logging.info(f"\n[{i}/{len(packages)}] Registering: {app_name}")
        logging.info(f"    Chocolatey package: {pkg_id}")

        if config.dry_run:
            logging.info(f"    [DRY-RUN] Would run: choco install {pkg_id} -y --force")
            successful.append(match)
            continue

        cmd = ["choco", "install", pkg_id, "-y", "--force"]
        _, stderr, code = runner(cmd)

        if code == 0:
            logging.info("    Successfully registered")
            successful.append(match)
        else:
            logging.error("    Registration failed")
            if stderr:
                logging.error(f"    Error: {stderr[:200]}")
            failed.append(match)

        if i < len(packages):
            time.sleep(0.5)

    logging.info("\n" + "=" * 70)
    logging.info("  REGISTRATION SUMMARY")
    logging.info("=" * 70)
    logging.info(f"\nSuccessfully registered: {len(successful)}")
    if failed:
        logging.warning(f"Failed: {len(failed)}")
        for match in failed:
            if isinstance(match, PackageMatch):
                logging.warning(f"  - {match.app_name} ({match.pkg_id})")
            else:
                logging.warning(f"  - {match.get('app_name')} ({match.get('choco_id')})")

    return len(failed) == 0


def register_interactive(
    matches: list[PackageMatch] | list[dict],
    config: Optional[ScanConfig] = None,
    *,
    input_fn: Optional[Callable[[str], str]] = None,
    runner: Optional[Callable] = None,
) -> bool:
    """Present the user with an interactive registration menu."""
    if input_fn is None:
        input_fn = input  # resolved at call time so patch('builtins.input') works
    if config is None:
        config = ScanConfig()

    logging.info("\n" + "=" * 70)
    logging.info("  REGISTRATION")
    logging.info("=" * 70)
    logging.info("\nRegistration options:")
    logging.info("  1. Register all packages automatically")
    logging.info("  2. Review and select packages individually")
    logging.info("  3. Export to batch file (manual registration)")
    logging.info("  4. Exit without registering")

    while True:
        choice = input_fn("\nSelect option (1-4): ").strip()
        if choice in ["1", "2", "3", "4"]:
            break

    if choice == "4":
        logging.info("\nExiting without registration.")
        return True

    if choice == "3":
        return export_to_batch(matches, input_fn=input_fn)

    packages_to_register: list = []

    if choice == "1":
        packages_to_register = list(matches)

    elif choice == "2":
        for i, match in enumerate(matches, 1):
            app_name = match.app_name if isinstance(match, PackageMatch) else match.get("app_name", "")
            while True:
                response = input_fn(
                    f"  [{i}/{len(matches)}] Register {app_name}? (y/n): "
                ).strip().lower()
                if response in ["y", "n"]:
                    break
            if response == "y":
                packages_to_register.append(match)

        if not packages_to_register:
            logging.info("\nNo packages selected. Exiting.")
            return True

    return register_packages(packages_to_register, config, runner=runner)
