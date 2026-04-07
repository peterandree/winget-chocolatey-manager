"""Tests for src/wincoman/matchers/winget.py (Issue #23)."""
import json
from unittest.mock import MagicMock

from wincoman.matchers.winget import WinGetManager


def _make_runner(stdout="", returncode=0):
    def runner(cmd, **kwargs):
        return stdout, "", returncode

    return runner


class TestWinGetManagerAvailability:
    def test_is_available_true_when_winget_responds(self):
        mgr = WinGetManager(runner=_make_runner("v1.6"))
        assert mgr.is_available() is True

    def test_is_available_false_when_winget_missing(self):
        mgr = WinGetManager(runner=_make_runner("", returncode=1))
        assert mgr.is_available() is False


class TestWinGetManagerListManaged:
    def _make_json_runner(self, packages):
        return _make_runner(json.dumps(packages))

    def test_returns_normalised_names(self):
        packages = [{"Name": "Git", "Id": "Git.Git"}, {"Name": "Python 3.12", "Id": "Python.Python"}]
        mgr = WinGetManager(runner=self._make_json_runner(packages))
        managed = mgr.list_managed()
        assert "git" in managed

    def test_empty_list_when_winget_fails(self):
        mgr = WinGetManager(runner=_make_runner("", returncode=1))
        assert mgr.list_managed() == set()

    def test_empty_list_on_invalid_json(self):
        mgr = WinGetManager(runner=_make_runner("not json"))
        assert mgr.list_managed() == set()

    def test_caches_result(self):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return json.dumps([{"Name": "Git", "Id": "Git.Git"}]), "", 0

        mgr = WinGetManager(runner=runner)
        # First call loads cache; second uses it
        calls_before = len(calls)
        mgr.list_managed()
        mgr.list_managed()
        # winget list should be called only once (for list_managed)
        list_calls = [c for c in calls if "list" in c]
        assert len(list_calls) == 1


class TestWinGetManagerIsManaged:
    def _manager_with(self, packages):
        runner = _make_runner(json.dumps(packages))
        return WinGetManager(runner=runner)

    def test_exact_match_returns_true(self):
        mgr = self._manager_with([{"Name": "Git", "Id": "Git.Git"}])
        assert mgr.is_managed("git") is True

    def test_no_match_returns_false(self):
        mgr = self._manager_with([{"Name": "Git", "Id": "Git.Git"}])
        assert mgr.is_managed("UnknownApp12345") is False

    def test_fuzzy_match_accepted_above_threshold(self):
        mgr = self._manager_with([{"Name": "GitHub Desktop", "Id": "GitHub.GitHubDesktop"}])
        # "github desktop" vs "GitHub Desktop" should score above default 60
        assert mgr.is_managed("GitHub Desktop") is True
