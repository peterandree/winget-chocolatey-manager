"""Package registration — dispatch install to the correct package manager.

:func:`register_packages` calls ``mgr.install()`` for each package, routing
to whichever manager owns the primary match.  :func:`register_interactive`
wraps it with a user-facing menu.

Both functions accept :class:`AppCandidates` (new), :class:`PackageMatch`
(single-manager), or legacy dicts for backward compatibility.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from wincoman.config import ScanConfig
from wincoman.matchers.base import AppCandidates, InstallablePackageManager, PackageMatch
from wincoman.reporter import export_to_batch
from wincoman.shell import run_command


def _resolve_match(entry: AppCandidates | PackageMatch | dict) -> tuple[str, PackageMatch | None]:
    """Return (app_name, PackageMatch) from any supported entry type."""
    if isinstance(entry, AppCandidates):
        return entry.app_name, entry.primary
    if isinstance(entry, PackageMatch):
        return entry.app_name, entry
    # Legacy dict
    app_name = entry.get("app_name", "")
    pkg_id = entry.get("choco_id", "")
    if pkg_id:
        return app_name, PackageMatch(
            app_name=app_name,
            app_version=entry.get("app_version", ""),
            pkg_id=pkg_id,
            pkg_version=entry.get("pkg_version", ""),
            version_mismatch=entry.get("version_mismatch", False),
            manager="chocolatey",
        )
    return app_name, None


def register_packages(
    packages: list[AppCandidates] | list[PackageMatch] | list[dict],
    config: Optional[ScanConfig] = None,
    *,
    managers: Optional[dict[str, InstallablePackageManager]] = None,
    runner: Optional[Callable] = None,
) -> bool:
    """Install each package via the appropriate manager.

    Uses ``managers[match.manager].install(match)`` when a manager map is
    provided; otherwise falls back to running the install command directly
    with the injectable *runner*.

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

    for i, entry in enumerate(packages, 1):
        app_name, match = _resolve_match(entry)
        if match is None:
            logging.warning(f"[{i}/{len(packages)}] Skipping {app_name}: no package match")
            continue

        pkg_id = match.pkg_id
        manager_name = match.manager

        logging.info(f"\n[{i}/{len(packages)}] Registering: {app_name}")
        logging.info(f"    Package: {pkg_id} via {manager_name}")

        if config.dry_run:
            logging.info(f"    [DRY-RUN] Would install {pkg_id} via {manager_name}")
            successful.append(entry)
            continue

        # Use injected manager if available
        mgr = managers.get(manager_name) if managers else None
        ok = False
        if mgr is not None:
            ok = mgr.install(match, dry_run=False)
        else:
            # Fallback: run choco install (legacy / no manager map)
            cmd = ["choco", "install", pkg_id, "-y", "--force"]
            _, stderr, code = runner(cmd)
            ok = code == 0
            if not ok:
                logging.error(f"    Install failed: {stderr[:200]}")

        if ok:
            logging.info("    Successfully registered")
            successful.append(entry)
        else:
            logging.error("    Registration failed")
            failed.append(entry)

        if i < len(packages):
            time.sleep(0.5)

    logging.info("\n" + "=" * 70)
    logging.info("  REGISTRATION SUMMARY")
    logging.info("=" * 70)
    logging.info(f"\nSuccessfully registered: {len(successful)}")
    if failed:
        logging.warning(f"Failed: {len(failed)}")
        for entry in failed:
            app_name, match = _resolve_match(entry)
            pkg_id = match.pkg_id if match else "?"
            logging.warning(f"  - {app_name} ({pkg_id})")

    return len(failed) == 0


def _prompt_manager_choice(
    entry: AppCandidates,
    i: int,
    total: int,
    input_fn: Callable[[str], str],
) -> Optional[PackageMatch]:
    """Ask user whether to register *entry* and which manager to use.

    Returns:
        The chosen :class:`PackageMatch`, or ``None`` if the user skips.
    """
    app_name = entry.app_name
    all_matches = entry.all_matches

    if len(all_matches) == 1:
        # Single option — just ask yes/no
        while True:
            response = input_fn(
                f"  [{i}/{total}] Register {app_name} "
                f"via {entry.primary.manager} [{entry.primary.pkg_id}]? (y/n): "
            ).strip().lower()
            if response in ["y", "n"]:
                break
        return entry.primary if response == "y" else None

    # Multiple options — show menu
    logging.info(f"\n  [{i}/{total}] {app_name}")
    for idx, m in enumerate(all_matches, 1):
        primary_flag = " (recommended)" if m is entry.primary else ""
        logging.info(f"    {idx}. {m.manager}: {m.pkg_id}{primary_flag}")
    logging.info(f"    {len(all_matches) + 1}. Skip")

    valid = [str(n) for n in range(1, len(all_matches) + 2)]
    while True:
        choice = input_fn(f"  Select (1-{len(all_matches) + 1}): ").strip()
        if choice in valid:
            break
    idx = int(choice) - 1
    if idx >= len(all_matches):
        return None
    return all_matches[idx]


def register_interactive(
    matches: list[AppCandidates] | list[PackageMatch] | list[dict],
    config: Optional[ScanConfig] = None,
    *,
    managers: Optional[dict[str, InstallablePackageManager]] = None,
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
        for i, entry in enumerate(matches, 1):
            if isinstance(entry, AppCandidates) and entry.alternatives:
                chosen = _prompt_manager_choice(entry, i, len(matches), input_fn)
                if chosen is not None:
                    # Wrap the chosen match in a single-candidate AppCandidates
                    packages_to_register.append(
                        AppCandidates(entry.app_name, entry.app_version, primary=chosen)
                    )
            else:
                app_name, _ = _resolve_match(entry)
                while True:
                    response = input_fn(
                        f"  [{i}/{len(matches)}] Register {app_name}? (y/n): "
                    ).strip().lower()
                    if response in ["y", "n"]:
                        break
                if response == "y":
                    packages_to_register.append(entry)

        if not packages_to_register:
            logging.info("\nNo packages selected. Exiting.")
            return True

    return register_packages(packages_to_register, config, managers=managers, runner=runner)
