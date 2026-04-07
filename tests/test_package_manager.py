"""Tests for register_unmanaged_apps.py"""
import sys
import os
import json
import subprocess
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


# ---------------------------------------------------------------------------
# Issue #15 — Registry scan deduplication
# ---------------------------------------------------------------------------

class TestGetInstalledProgramsDedup:
    def _run_with_json(self, programs_json: str):
        pm = PackageManager()
        with patch.object(PackageManager, 'run_command', return_value=(programs_json, '', 0)):
            pm.get_installed_programs()
        return pm.installed_programs

    def test_no_duplicates_when_unique(self):
        data = json.dumps([
            {'DisplayName': 'App A', 'DisplayVersion': '1.0', 'Publisher': 'X'},
            {'DisplayName': 'App B', 'DisplayVersion': '2.0', 'Publisher': 'Y'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 2

    def test_duplicates_removed(self):
        data = json.dumps([
            {'DisplayName': 'Git', 'DisplayVersion': '2.44', 'Publisher': 'GitForWindows'},
            {'DisplayName': 'Git', 'DisplayVersion': '2.44', 'Publisher': 'GitForWindows'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 1

    def test_first_occurrence_preferred(self):
        """HKLM 64-bit (first in list) should be kept over WOW6432Node duplicate."""
        data = json.dumps([
            {'DisplayName': 'MyApp', 'DisplayVersion': '64bit-version', 'Publisher': 'Pub'},
            {'DisplayName': 'MyApp', 'DisplayVersion': '32bit-version', 'Publisher': 'Pub'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 1
        assert result[0]['DisplayVersion'] == '64bit-version'

    def test_case_insensitive_dedup(self):
        data = json.dumps([
            {'DisplayName': 'MyApp', 'DisplayVersion': '1.0', 'Publisher': 'X'},
            {'DisplayName': 'myapp', 'DisplayVersion': '1.0', 'Publisher': 'X'},
            {'DisplayName': 'MYAPP', 'DisplayVersion': '1.0', 'Publisher': 'X'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Issue #14 — run_command timeout
# ---------------------------------------------------------------------------

class TestRunCommandTimeout:
    def test_timeout_returns_error_tuple(self):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=['choco'], timeout=60)):
            stdout, stderr, code = PackageManager.run_command(['choco', 'search', 'something'])
        assert stdout == ''
        assert 'timed out' in stderr.lower()
        assert code == 1

    def test_timeout_passed_to_subprocess(self):
        with patch('subprocess.run', return_value=MagicMock(stdout='ok', stderr='', returncode=0)) as mock_run:
            PackageManager.run_command(['choco', '--version'])
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert 'timeout' in kwargs
        assert kwargs['timeout'] == PackageManager.COMMAND_TIMEOUT

    def test_custom_timeout_respected(self):
        with patch('subprocess.run', return_value=MagicMock(stdout='ok', stderr='', returncode=0)) as mock_run:
            PackageManager.run_command(['choco', '--version'], timeout=5)
        _, kwargs = mock_run.call_args
        assert kwargs['timeout'] == 5
