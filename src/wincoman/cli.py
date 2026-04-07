"""CLI entry point for wincoman.

This module is a stub. Full implementation arrives in Issue #29.
"""
import sys


def main() -> None:
    """Entry point registered as the ``wincoman`` console script."""
    # Delegate to the existing implementation until Issue #29 wires the
    # full src/wincoman pipeline.
    import os
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from register_unmanaged_apps import main as _legacy_main
    _legacy_main()
