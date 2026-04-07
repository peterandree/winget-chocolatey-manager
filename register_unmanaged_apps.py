#!/usr/bin/env python3
"""
Deprecated: Use ``wincoman`` CLI instead.

This file is kept for backward compatibility only and will be removed in v2.0.
Run ``uv run wincoman --help`` for usage.
"""
import warnings

warnings.warn(
    "register_unmanaged_apps.py is deprecated. Use 'uv run wincoman' instead.",
    DeprecationWarning,
    stacklevel=1,
)

from wincoman.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
