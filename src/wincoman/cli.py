"""CLI entry point for wincoman."""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

from wincoman.config import ScanConfig


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wincoman",
        description="Find apps not managed by WinGet/Chocolatey and register them.",
    )
    parser.add_argument("--auto", action="store_true",
                        help="Register all matches without prompting.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview all actions without executing any choco install calls.")
    parser.add_argument("--export-only", action="store_true",
                        help="Always write a batch file; skip the interactive prompt.")
    parser.add_argument("--output", metavar="PATH",
                        help="Batch file output path (used with --export-only).")
    parser.add_argument("--log-file", metavar="PATH",
                        help="Write log output to this file in addition to stdout.")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress INFO-level output.")
    parser.add_argument("--exclude-microsoft", action="store_true",
                        help="Filter out Microsoft/Windows-published apps.")
    parser.add_argument("--min-score", type=int, default=0, metavar="INT",
                        help="Minimum fuzzy-match confidence threshold (0-100, default 60).")
    parser.add_argument("--use-cache", action="store_true",
                        help="Skip full scan and use cached results from a previous run.")
    parser.add_argument("--cache-file", metavar="PATH",
                        help="Path to the JSON cache file.")
    parser.add_argument("--search-workers", type=int, default=5, metavar="N",
                        help="Number of concurrent Chocolatey search threads (default 5).")
    return parser


def _configure_logging(config: ScanConfig) -> None:
    level = logging.WARNING if config.quiet else logging.INFO
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(level)
    formatter = logging.Formatter("%(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)
    if config.log_file:
        fh = logging.FileHandler(config.log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)


def main() -> None:
    """Entry point registered as the ``wincoman`` console script."""
    parser = _build_arg_parser()
    args = parser.parse_args()
    config = ScanConfig.from_namespace(args)
    _configure_logging(config)

    from wincoman.runner import Orchestrator

    try:
        orchestrator = Orchestrator(config)
        if config.dry_run:
            logging.info("DRY-RUN mode — no packages will be installed.")
        sys.exit(orchestrator.run())
    except KeyboardInterrupt:
        logging.warning("Interrupted by user. Exiting...")
        sys.exit(130)
    except Exception as exc:
        logging.error(f"Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
