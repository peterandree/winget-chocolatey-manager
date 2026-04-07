"""Shared pytest fixtures and path setup.

Makes ``register_unmanaged_apps`` importable without per-test sys.path hacks,
since it lives in the repo root (not inside src/).
"""
import os
import sys

# Add repo root to sys.path so legacy tests can still import PackageManager
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
