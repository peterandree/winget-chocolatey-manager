"""Shell command execution utilities.

Provides a module-level ``run_command`` function used by all adapter modules,
and ``get_choco_major_version`` for Chocolatey version detection.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Optional

# Hard timeout (seconds) for external commands.  Adapters may pass a shorter
# timeout for quick operations (e.g. get_choco_major_version uses 15 s).
DEFAULT_TIMEOUT = 60


def run_command(
    cmd: list[str] | str,
    *,
    capture_output: bool = True,
    shell: bool = False,
    timeout: Optional[int] = None,
) -> tuple[str, str, int]:
    """Run *cmd* and return ``(stdout, stderr, returncode)``.

    Never raises — all subprocess errors are converted to a non-zero return
    code with the error message in *stderr*.
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="ignore",
            shell=shell,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        cmd_str = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
        logging.warning(f"Command timed out after {timeout}s: {cmd_str}")
        return "", f"Command timed out after {timeout}s", 1
    except FileNotFoundError:
        first = cmd if isinstance(cmd, str) else cmd[0]
        return "", f"Command not found: {first}", 1
    except Exception as exc:  # noqa: BLE001
        return "", str(exc), 1


def get_choco_major_version() -> int:
    """Return the Chocolatey major version number, or 0 if undetermined."""
    try:
        result = subprocess.run(
            ["choco", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
        )
        version_str = result.stdout.strip()
        return int(version_str.split(".")[0])
    except Exception:  # noqa: BLE001
        return 0
