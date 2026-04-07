#!/usr/bin/env python3
"""
Chocolatey Registration Script for Apps Not Managed by WinGet
This script finds apps that aren't in WinGet and registers them with Chocolatey
Version 1.0 - Checks for unregistered apps and creates registration script
Version 1.1 - Added error handling and direct registration

Deprecated: This file is a backward-compatibility shim. All logic is being
migrated to the ``src/wincoman/`` package (Issue #29). Use ``wincoman`` CLI.
"""

import subprocess
import json
import logging
import re
import sys
import time
import argparse
from typing import List, Dict, Set, Tuple, Optional

# ── Delegate to new modules where available ──────────────────────────────────
from wincoman.shell import run_command as _shell_run_command
from wincoman.shell import get_choco_major_version as _shell_get_choco_major_version
from wincoman.scoring import fuzzy_score as _scoring_fuzzy_score
from wincoman.scoring import normalize_name as _scoring_normalize_name
from wincoman.scoring import versions_differ as _scoring_versions_differ
from wincoman.config import ScanConfig as _ScanConfig
from wincoman.registry import scan_installed_programs as _registry_scan
from wincoman.cache import save_cache as _cache_save, load_cache as _cache_load
from wincoman.cache import default_cache_path as _cache_default_path
from wincoman.detector import find_unmanaged as _detector_find_unmanaged
from wincoman.reporter import display_results as _reporter_display_results
from wincoman.reporter import export_to_batch as _reporter_export_to_batch
from wincoman.installer import register_packages as _installer_register_packages

try:
    from rapidfuzz import fuzz as _fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RAPIDFUZZ_AVAILABLE = False

class PackageManager:
    """Main package manager class with error handling"""

    def __init__(self, exclude_microsoft: bool = False, dry_run: bool = False,
                 min_score: int = 0):
        self.winget_apps = {}
        self.choco_packages = set()
        self.scoop_packages: Set[str] = set()
        self.installed_programs = []
        self.unmanaged_apps = []
        self.matches = []
        # When True, Microsoft/Windows-published apps are filtered out during
        # registry scan, matching the old default behaviour.  Off by default so
        # apps like VS Code, PowerToys, Windows Terminal etc. are included.
        self.exclude_microsoft = exclude_microsoft
        # When True, no choco install calls are executed; actions are only previewed.
        self.dry_run = dry_run
        # Override the class-level FUZZY_MATCH_THRESHOLD when > 0.
        if min_score > 0:
            self.FUZZY_MATCH_THRESHOLD = min_score

    # Default cache file path (~/.wincoman/state.json)
    @staticmethod
    def _default_cache_path() -> str:
        return _cache_default_path()

    log = logging.getLogger(__name__)

    # Default timeout (seconds) for external commands. choco search can be slow on
    # large repositories, but 60 s is plenty; increase if needed.
    COMMAND_TIMEOUT = 60
    # Delay (seconds) between successive choco search calls to avoid rate-limiting.
    SEARCH_DELAY = 0.1
    # Minimum fuzzy-match score (0-100) required to consider a Chocolatey package
    # a match for an installed app name.
    FUZZY_MATCH_THRESHOLD = 60

    @staticmethod
    def run_command(cmd: List[str], capture_output=True, shell=False, timeout: Optional[int] = None) -> Tuple[str, str, int]:
        """Run a command and return stdout, stderr, and return code.

        Delegates to :func:`wincoman.shell.run_command`.
        """
        return _shell_run_command(
            cmd,
            capture_output=capture_output,
            shell=shell,
            timeout=timeout if timeout is not None else PackageManager.COMMAND_TIMEOUT,
        )

    @staticmethod
    def get_choco_major_version() -> int:
        """Return the Chocolatey major version number, or 0 if undetermined.

        Delegates to :func:`wincoman.shell.get_choco_major_version`.
        """
        return _shell_get_choco_major_version()

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalise app name.  Delegates to :func:`wincoman.scoring.normalize_name`."""
        return _scoring_normalize_name(name)

    @staticmethod
    def fuzzy_score(a: str, b: str) -> int:
        """Return fuzzy similarity score.  Delegates to :func:`wincoman.scoring.fuzzy_score`."""
        return _scoring_fuzzy_score(a, b)

    def check_prerequisites(self) -> bool:
        """Check if required tools are available"""
        logging.info("\n" + "=" * 70)
        logging.info("  Checking Prerequisites")
        logging.info("=" * 70)

        # Check WinGet
        logging.info("\nChecking WinGet...")
        stdout, stderr, code = self.run_command(['winget', '--version'])
        if code != 0:
            logging.error("❌ WinGet is not available!")
            logging.error("   WinGet should be pre-installed on Windows 11.")
            logging.error("   For Windows 10, install from: https://aka.ms/getwinget")
            return False
        logging.info(f"✅ WinGet is installed (version: {stdout.strip()})")

        # Check Chocolatey
        logging.info("\nChecking Chocolatey...")
        stdout, stderr, code = self.run_command(['choco', '--version'])
        if code != 0:
            logging.error("❌ Chocolatey is not installed!")
            logging.error("   Install from: https://chocolatey.org/install")
            return False
        logging.info(f"✅ Chocolatey is installed (version: {stdout.strip()})")

        # Check for admin privileges — choco install requires elevation; fail fast.
        logging.info("\nChecking administrator privileges...")
        if sys.platform == 'win32':
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if not is_admin:
                logging.error("❌ Not running as Administrator!")
                logging.error("   choco install requires elevation. Please re-run this script")
                logging.error("   from an elevated (Administrator) PowerShell or Command Prompt.")
                return False
            else:
                logging.info("✅ Running with Administrator privileges")

        return True

    def get_winget_packages(self) -> bool:
        """Get all packages managed by WinGet"""
        logging.info("\n" + "=" * 70)
        logging.info("  Step 1/5: Checking WinGet Managed Packages")
        logging.info("=" * 70)

        # --output json is available since WinGet 1.2 and gives reliable structured
        # output that isn't affected by fixed-width column formatting.
        stdout, stderr, code = self.run_command(
            ['winget', 'list', '--output', 'json', '--accept-source-agreements']
        )

        if code != 0:
            logging.error(f"❌ Failed to get WinGet packages!\n   Error: {stderr}")
            return False

        try:
            packages = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            logging.error("❌ Failed to parse WinGet JSON output!")
            return False

        for pkg in packages:
            name = pkg.get('Name', '') or ''
            name = name.strip()
            if name:
                self.winget_apps[name.lower()] = {'name': name, 'id': pkg.get('Id', '')}

        if not self.winget_apps:
            logging.warning("⚠️  Warning: No WinGet packages detected")
            logging.warning("   This is unusual. Continuing anyway...")
        else:
            logging.info(f"✅ Found {len(self.winget_apps)} apps managed by WinGet")

        return True

    def get_installed_programs(self) -> bool:
        """Get all installed programs from Windows Registry.

        Delegates to :func:`wincoman.registry.scan_installed_programs`.
        """
        logging.info("\n" + "=" * 70)
        logging.info("  Step 2/5: Scanning Installed Programs")
        logging.info("=" * 70)

        config = _ScanConfig(exclude_microsoft=self.exclude_microsoft)

        # Inject run_command so existing tests can still mock PackageManager.run_command
        def _runner(cmd, **kwargs):
            return self.run_command(cmd, **kwargs)

        programs = _registry_scan(config, runner=_runner)
        if not programs:
            # _registry_scan already logged the error
            return False

        self.installed_programs = programs
        logging.info(f"✅ Found {len(self.installed_programs)} installed programs")
        return True

    def get_chocolatey_packages(self) -> bool:
        """Get packages already registered with Chocolatey"""
        logging.info("\n" + "=" * 70)
        logging.info("  Step 3/5: Checking Chocolatey Packages")
        logging.info("=" * 70)

        # --limit-output is deprecated in Chocolatey v2.x; use bare 'choco list' there.
        choco_major = self.get_choco_major_version()
        if choco_major >= 2:
            cmd = ['choco', 'list']
        else:
            cmd = ['choco', 'list', '--limit-output']

        stdout, stderr, code = self.run_command(cmd)

        if code != 0:
            logging.error(f"❌ Failed to get Chocolatey packages!\n   Error: {stderr}")
            return False

        for line in stdout.split('\n'):
            line = line.strip()
            if not line:
                continue

            parts = line.split('|')
            if len(parts) >= 2:
                normalized = self.normalize_name(parts[0])
                if normalized:
                    self.choco_packages.add(normalized)

        logging.info(f"✅ Found {len(self.choco_packages)} packages in Chocolatey")
        return True

    def get_scoop_packages(self) -> bool:
        """Get packages installed via Scoop (optional — skipped if Scoop not found)."""
        stdout, stderr, code = self.run_command(['scoop', 'list'], timeout=30)
        if code != 0:
            # Scoop is not installed or not on PATH — skip gracefully.
            logging.info("ℹ️  Scoop not found or unavailable — skipping Scoop check.")
            return True

        for line in stdout.split('\n'):
            parts = line.split()
            if parts:
                name = parts[0].strip().lower()
                if name and name not in ('name', '----'):
                    self.scoop_packages.add(name)

        if self.scoop_packages:
            logging.info(f"✅ Found {len(self.scoop_packages)} packages in Scoop")
        return True

    def save_cache(self, cache_path: Optional[str] = None) -> None:
        """Persist scan results. Delegates to :func:`wincoman.cache.save_cache`."""
        if cache_path is None:
            cache_path = self._default_cache_path()
        _cache_save(cache_path, self.unmanaged_apps, self.matches)

    def load_cache(self, cache_path: Optional[str] = None) -> bool:
        """Load scan results. Delegates to :func:`wincoman.cache.load_cache`."""
        if cache_path is None:
            cache_path = self._default_cache_path()
        result = _cache_load(cache_path)
        if result is None:
            return False
        self.unmanaged_apps, self.matches = result
        return True

    @staticmethod
    def _versions_differ(installed: str, choco: str) -> bool:
        """Delegates to :func:`wincoman.scoring.versions_differ`."""
        return _scoring_versions_differ(installed, choco)

    def _is_managed_by_winget(self, display_name: str) -> bool:
        """Return True if the app name fuzzy-matches a WinGet-managed package."""
        name_lower = display_name.lower()
        # Fast exact check first
        if name_lower in self.winget_apps:
            return True
        # Fuzzy fallback for minor spelling/punctuation differences
        for wg_name in self.winget_apps:
            if self.fuzzy_score(display_name, wg_name) >= self.FUZZY_MATCH_THRESHOLD:
                return True
        return False

    def find_unmanaged_apps(self) -> bool:
        """Find apps not managed by WinGet or Chocolatey.

        Delegates to :func:`wincoman.detector.find_unmanaged`.
        """
        logging.info("\n" + "=" * 70)
        logging.info("  Step 4/5: Finding Unmanaged Apps")
        logging.info("=" * 70)

        # Build minimal adapter shims from existing state for backward compat
        class _WingetShim:
            def __init__(self, pm):
                self._pm = pm

            def is_managed(self, display_name):
                return self._pm._is_managed_by_winget(display_name)

        class _ChocoShim:
            def __init__(self, pm):
                self._pm = pm

            def is_managed(self, display_name):
                from wincoman.scoring import normalize_name
                return normalize_name(display_name) in self._pm.choco_packages

        class _ScoopShim:
            def __init__(self, pm):
                self._pm = pm

            def is_managed(self, display_name):
                name_lower = display_name.lower()
                norm = self._pm.normalize_name(display_name)
                return (
                    name_lower in self._pm.scoop_packages
                    or norm in self._pm.scoop_packages
                )

        managers = [_WingetShim(self), _ChocoShim(self), _ScoopShim(self)]
        self.unmanaged_apps = _detector_find_unmanaged(self.installed_programs, managers)

        logging.info(f"✅ Found {len(self.unmanaged_apps)} apps not managed by WinGet or Chocolatey")

        if not self.unmanaged_apps:
            logging.info("\n🎉 All your apps are already managed!")
            logging.info("   No action needed.")
            return False

        return True

    def search_chocolatey_matches(self) -> bool:
        """Search for Chocolatey packages for unmanaged apps"""
        logging.info("\n" + "=" * 70)
        logging.info("  Step 5/5: Searching Chocolatey Repository")
        logging.info("=" * 70)
        logging.info("\nThis may take a few minutes...")

        # --limit-output is deprecated in Chocolatey v2.x.
        choco_major = self.get_choco_major_version()
        limit_output_flag = [] if choco_major >= 2 else ['--limit-output']

        total = len(self.unmanaged_apps)
        for i, app in enumerate(self.unmanaged_apps, 1):
            if i % 5 == 0 or i == total:
                logging.info(f"Progress: {i}/{total} apps processed...")

            # Try exact search first
            stdout, stderr, code = self.run_command(
                ['choco', 'search', app['name'], '--exact'] + limit_output_flag
            )

            package_id = None
            package_version = None

            if code == 0 and stdout.strip():
                lines = stdout.strip().split('\n')
                if lines:
                    parts = lines[0].split('|')
                    if len(parts) >= 2:
                        package_id = parts[0]
                        package_version = parts[1]

            # Try approximate search if exact failed — score every candidate
            # against the installed app name and only accept results above threshold.
            if not package_id:
                stdout, stderr, code = self.run_command(
                    ['choco', 'search', app['name']] + limit_output_flag
                )

                if code == 0 and stdout.strip():
                    best_id = None
                    best_version = None
                    best_score = 0
                    for line in stdout.strip().split('\n'):
                        parts = line.split('|')
                        if len(parts) >= 2:
                            candidate_id = parts[0].strip()
                            score = self.fuzzy_score(app['name'], candidate_id)
                            if score > best_score:
                                best_score = score
                                best_id = candidate_id
                                best_version = parts[1].strip()
                    if best_score >= self.FUZZY_MATCH_THRESHOLD:
                        package_id = best_id
                        package_version = best_version

            if package_id:
                version_mismatch = self._versions_differ(
                    app.get('version', ''), package_version or ''
                )
                self.matches.append({
                    'app_name': app['name'],
                    'app_version': app['version'],
                    'choco_id': package_id,
                    'choco_version': package_version,
                    'version_mismatch': version_mismatch,
                })

            # Brief delay between network calls to avoid rate-limiting.
            if i < total:
                time.sleep(self.SEARCH_DELAY)

        if not self.matches:
            logging.warning("\n⚠️  No matching Chocolatey packages found.")
            logging.warning("   Your apps might be too specialized or not available in Chocolatey.")
            return False

        logging.info(f"\n✅ Found {len(self.matches)} matching packages in Chocolatey")
        return True

    def display_results(self):
        """Display the discovered matches. Delegates to :func:`wincoman.reporter.display_results`."""
        _reporter_display_results(self.matches)

    def _register_packages(self, packages_to_register: List[Dict]) -> bool:
        """Execute choco install. Delegates to :func:`wincoman.installer.register_packages`."""
        config = _ScanConfig(dry_run=self.dry_run)
        return _installer_register_packages(packages_to_register, config, runner=self.run_command)

    def register_packages_interactive(self) -> bool:
        """Interactively register packages with Chocolatey"""
        logging.info("\n" + "=" * 70)
        logging.info("  REGISTRATION")
        logging.info("=" * 70)

        logging.info("\nRegistration options:")
        logging.info("  1. Register all packages automatically")
        logging.info("  2. Review and select packages individually")
        logging.info("  3. Export to batch file (manual registration)")
        logging.info("  4. Exit without registering")

        while True:
            choice = input("\nSelect option (1-4): ").strip()
            if choice in ['1', '2', '3', '4']:
                break
            logging.info("Invalid choice. Please enter 1, 2, 3, or 4.")

        if choice == '4':
            logging.info("\nExiting without registration.")
            return True

        if choice == '3':
            return self.export_to_batch()

        packages_to_register = []

        if choice == '1':
            packages_to_register = self.matches
            logging.info(f"\nRegistering all {len(packages_to_register)} packages...")

        elif choice == '2':
            logging.info("\nSelect packages to register:")
            for i, match in enumerate(self.matches, 1):
                while True:
                    response = input(
                        f"  [{i}/{len(self.matches)}] Register {match['app_name']}? (y/n): "
                    ).strip().lower()
                    if response in ['y', 'n']:
                        break
                    logging.info("      Please enter 'y' or 'n'")

                if response == 'y':
                    packages_to_register.append(match)

            if not packages_to_register:
                logging.info("\nNo packages selected. Exiting.")
                return True

        return self._register_packages(packages_to_register)

    def export_to_batch(self, output_path: Optional[str] = None) -> bool:
        """Export registration commands to a batch file.

        Delegates to :func:`wincoman.reporter.export_to_batch`.
        """
        return _reporter_export_to_batch(self.matches, output_path)

    def run(self, auto: bool = False, export_only: bool = False,
            output_path: Optional[str] = None,
            use_cache: bool = False, cache_path: Optional[str] = None) -> int:
        """Main execution flow"""
        logging.info("=" * 70)
        logging.info("  Chocolatey Registration for Apps Not Managed by WinGet")
        logging.info("  Version 1.2 - With argparse, logging, and dry-run support")
        logging.info("=" * 70)

        if use_cache:
            if not self.load_cache(cache_path):
                logging.warning("Cache unavailable — falling back to full scan.")
                use_cache = False

        if not use_cache:
            # Check prerequisites
            if not self.check_prerequisites():
                return 1

            # Step 1: Get WinGet packages
            if not self.get_winget_packages():
                logging.error("\n❌ Failed at Step 1. Cannot continue.")
                return 1

            # Step 1b: Get Scoop packages (optional)
            self.get_scoop_packages()

            # Step 2: Get installed programs
            if not self.get_installed_programs():
                logging.error("\n❌ Failed at Step 2. Cannot continue.")
                return 1

            # Step 3: Get Chocolatey packages
            if not self.get_chocolatey_packages():
                logging.error("\n❌ Failed at Step 3. Cannot continue.")
                return 1

            # Step 4: Find unmanaged apps
            if not self.find_unmanaged_apps():
                return 0

            # Step 5: Search for matches
            if not self.search_chocolatey_matches():
                return 0

            # Save results to cache for future --use-cache runs
            self.save_cache(cache_path)

        if not self.matches:
            logging.info("\n🎉 No unmanaged apps with Chocolatey matches found.")
            return 0

        # Display results
        self.display_results()

        if self.dry_run:
            logging.info("\n🔍 DRY-RUN: no packages were installed.")
            return 0

        # Registration
        if export_only:
            return 0 if self.export_to_batch(output_path=output_path) else 1

        if auto:
            return 0 if self._register_packages(self.matches) else 1

        if not self.register_packages_interactive():
            logging.warning("\n⚠️  Registration completed with some errors.")
            return 1

        logging.info("\n" + "=" * 70)
        logging.info("✅ Script completed successfully!")
        logging.info("=" * 70)
        return 0

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='register_unmanaged_apps',
        description='Find apps not managed by WinGet/Chocolatey and register them.',
    )
    parser.add_argument(
        '--auto', action='store_true',
        help='Register all matches without prompting.',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview all actions without executing any choco install calls.',
    )
    parser.add_argument(
        '--export-only', action='store_true',
        help='Always write a batch file; skip the interactive prompt.',
    )
    parser.add_argument(
        '--output', metavar='PATH',
        help='Batch file output path (used with --export-only). '
             'Defaults to a timestamped name.',
    )
    parser.add_argument(
        '--log-file', metavar='PATH',
        help='Write log output to this file in addition to stdout.',
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress INFO-level output (only warnings and errors are shown).',
    )
    parser.add_argument(
        '--exclude-microsoft', action='store_true',
        help='Filter out Microsoft/Windows-published apps (restores old behaviour).',
    )
    parser.add_argument(
        '--min-score', type=int, default=0, metavar='INT',
        help='Minimum fuzzy-match confidence threshold (0-100, default 60).',
    )
    parser.add_argument(
        '--use-cache', action='store_true',
        help='Skip full scan and use cached results from a previous run.',
    )
    parser.add_argument(
        '--cache-file', metavar='PATH',
        help='Path to the JSON cache file (default: ~/.winget-choco-manager/state.json).',
    )
    return parser


def _configure_logging(quiet: bool, log_file: Optional[str]) -> None:
    level = logging.WARNING if quiet else logging.INFO
    root = logging.getLogger()
    # Remove any existing handlers so we can reconfigure (e.g. in tests).
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(level)
    formatter = logging.Formatter('%(message)s')
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)
    if log_file:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(formatter)
        root.addHandler(fh)


def main():
    """Entry point — delegates to wincoman.cli.main() (deprecated shim)."""
    from wincoman.cli import main as _wincoman_main
    _wincoman_main()

if __name__ == '__main__':
    main()
