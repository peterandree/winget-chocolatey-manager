"""Tests for register_unmanaged_apps.py"""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock, call
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from register_unmanaged_apps import PackageManager


# ---------------------------------------------------------------------------
# Issue #17 — display_results() truncation off-by-one
# ---------------------------------------------------------------------------

class TestDisplayResults:
    def _manager_with_matches(self, matches):
        pm = PackageManager()
        pm.matches = matches
        return pm

    def test_short_name_not_truncated(self, capsys):
        pm = self._manager_with_matches([{'app_name': 'ShortApp', 'choco_id': 'shortapp'}])
        pm.display_results()
        out = capsys.readouterr().out
        assert 'ShortApp' in out
        assert '...' not in out

    def test_exactly_39_chars_not_truncated(self, capsys):
        name = 'A' * 39
        pm = self._manager_with_matches([{'app_name': name, 'choco_id': 'pkg'}])
        pm.display_results()
        out = capsys.readouterr().out
        assert '...' not in out

    def test_name_40_chars_is_truncated(self, capsys):
        name = 'A' * 40
        pm = self._manager_with_matches([{'app_name': name, 'choco_id': 'pkg'}])
        pm.display_results()
        out = capsys.readouterr().out
        assert '...' in out

    def test_truncated_display_fits_in_40_chars(self, capsys):
        name = 'A' * 80
        pm = self._manager_with_matches([{'app_name': name, 'choco_id': 'pkg'}])
        pm.display_results()
        out = capsys.readouterr().out
        # Find the line with truncated name
        for line in out.split('\n'):
            if '...' in line and 'pkg' in line:
                # The display portion before choco_id column should be <= 40 chars
                # The format is f"{app_display:<40} {choco_id:<30}"
                # So the app_display part occupies positions 0-39
                display_part = line[:40].rstrip()
                assert len(display_part) <= 39, f"Truncated name overflows column: '{display_part}'"
                break
