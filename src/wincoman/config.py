"""ScanConfig dataclass — single source of truth for all runtime configuration.

Every tunable parameter lives here; all adapter and orchestrator code receives
a ``ScanConfig`` instance rather than individual keyword arguments.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Optional


def _default_cache_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".wincoman", "state.json")


@dataclass
class ScanConfig:
    # ── Filtering ────────────────────────────────────────────────────────────
    exclude_microsoft: bool = False
    """Filter Microsoft/Windows-published apps out of the registry scan."""

    # ── Fuzzy matching ───────────────────────────────────────────────────────
    min_score: int = 60
    """Minimum WRatio score (0-100) to accept a package-repo candidate."""

    # ── Execution behaviour ──────────────────────────────────────────────────
    dry_run: bool = False
    """Preview all actions; never execute choco install."""

    auto: bool = False
    """Register all matches without interactive prompts."""

    export_only: bool = False
    """Always write a batch file; skip the interactive registration menu."""

    output_path: Optional[str] = None
    """Batch-file destination for --export-only (timestamped default)."""

    # ── Cache ────────────────────────────────────────────────────────────────
    use_cache: bool = False
    """Skip full scan and reuse persisted results from a previous run."""

    cache_path: str = field(default_factory=_default_cache_path)
    """JSON file used for scan-result persistence."""

    # ── Subprocess tuning ────────────────────────────────────────────────────
    command_timeout: int = 60
    """Hard timeout (seconds) for all external commands."""

    search_delay: float = 0.1
    """Delay (seconds) between successive choco search calls."""

    # ── Logging ──────────────────────────────────────────────────────────────
    quiet: bool = False
    """Suppress INFO output; show only warnings and errors."""

    log_file: Optional[str] = None
    """Tee log output to this file in addition to stdout."""

    @classmethod
    def from_namespace(cls, ns: argparse.Namespace) -> "ScanConfig":
        """Construct a ``ScanConfig`` from an ``argparse.Namespace``."""
        return cls(
            exclude_microsoft=getattr(ns, "exclude_microsoft", False),
            min_score=getattr(ns, "min_score", 0) or 0,
            dry_run=getattr(ns, "dry_run", False),
            auto=getattr(ns, "auto", False),
            export_only=getattr(ns, "export_only", False),
            output_path=getattr(ns, "output", None),
            use_cache=getattr(ns, "use_cache", False),
            cache_path=getattr(ns, "cache_file", None) or _default_cache_path(),
            quiet=getattr(ns, "quiet", False),
            log_file=getattr(ns, "log_file", None),
        )
