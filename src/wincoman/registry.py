"""Windows registry scanner.

Provides :func:`scan_installed_programs` which runs a PowerShell query against
the three standard Uninstall registry hives and returns a deduplicated list of
installed programs.

The PowerShell script body is a named constant so it can be audited and tested
independently of the scan entry-point.
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from wincoman.config import ScanConfig
from wincoman.shell import run_command

# Registry hive keys queried by the scanner (64-bit, 32-bit WOW64, per-user).
_HIVES = (
    r"HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
    r"HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
)

# Base PowerShell script (no Microsoft filter).
_REGISTRY_QUERY_BASE = r"""
$UninstallKeys = @(
    "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
    "HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
    "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"
)
Get-ItemProperty $UninstallKeys -ErrorAction SilentlyContinue |
    Where-Object { {filter} } |
    Select-Object DisplayName, DisplayVersion, Publisher |
    ConvertTo-Json -Compress
"""

_FILTER_ALL = "$_.DisplayName"
_FILTER_NO_MICROSOFT = (
    "$_.DisplayName -and "
    "$_.DisplayName -notmatch '^(Microsoft|Windows|Update|Hotfix|KB[0-9]|Security)'"
)


def scan_installed_programs(
    config: Optional[ScanConfig] = None,
    *,
    runner: Optional[Callable] = None,
) -> list[dict]:
    """Return a deduplicated list of installed programs from the Windows registry.

    Args:
        config: Controls the ``exclude_microsoft`` filter and timeout.
        runner: Injectable subprocess wrapper (default: ``shell.run_command``).

    Returns:
        List of dicts with keys ``DisplayName``, ``DisplayVersion``, ``Publisher``.
    """
    if config is None:
        config = ScanConfig()
    if runner is None:
        runner = run_command

    where_filter = _FILTER_NO_MICROSOFT if config.exclude_microsoft else _FILTER_ALL
    ps_script = _REGISTRY_QUERY_BASE.replace("{filter}", where_filter)

    stdout, stderr, code = runner(["powershell", "-Command", ps_script])

    if code != 0:
        logging.error(f"Failed to retrieve installed programs: {stderr}")
        return []

    if not stdout.strip():
        logging.error("No installed programs found — possible permission issue.")
        return []

    try:
        programs = json.loads(stdout)
        if isinstance(programs, dict):
            programs = [programs]
        return _deduplicate(programs)
    except json.JSONDecodeError as exc:
        logging.error(f"Failed to parse installed programs: {exc}")
        return []


def _deduplicate(programs: list[dict]) -> list[dict]:
    """Return *programs* with duplicate DisplayName entries removed.

    The first occurrence of each name is kept (case-insensitive comparison).
    The caller controls the ordering — the PowerShell script queries hives in
    the order HKLM 64-bit → WOW6432Node → HKCU, so the first occurrence is
    the preferred 64-bit entry.
    """
    seen: dict[str, bool] = {}
    result: list[dict] = []
    for prog in programs:
        key = (prog.get("DisplayName") or "").strip().lower()
        if key and key not in seen:
            seen[key] = True
            result.append(prog)
    return result
