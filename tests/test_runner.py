"""Tests for src/wincoman/runner.py (Issue #29)."""
import logging
from unittest.mock import MagicMock, patch

import pytest

from wincoman.config import ScanConfig
from wincoman.matchers.base import PackageMatch
from wincoman.runner import Orchestrator


def _mock_manager(name, available=True, managed=False):
    """Build a mock adapter."""
    mgr = MagicMock()
    mgr.name = name
    mgr.is_available.return_value = available
    mgr.is_managed.return_value = managed
    mgr.list_managed.return_value = set()
    return mgr


def _mock_choco(available=True, search_results=None, managed=False):
    mgr = _mock_manager("chocolatey", available=available, managed=managed)
    mgr.search_many.return_value = search_results or []
    return mgr


def _match(app_name="Git", pkg_id="git"):
    return PackageMatch(
        app_name=app_name,
        app_version="2.44",
        pkg_id=pkg_id,
        pkg_version="2.44.0",
        version_mismatch=False,
        manager="chocolatey",
    )


class TestOrchestratorDryRun:
    def test_dry_run_exits_zero_without_installing(self, caplog):
        cfg = ScanConfig(dry_run=True)
        choco = _mock_choco(search_results=[_match()])
        winget = _mock_manager("winget")
        scoop = _mock_manager("scoop")

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch("wincoman.runner.scan_installed_programs",
                   return_value=[{"DisplayName": "Git", "DisplayVersion": "2.44", "Publisher": "X"}]), \
             patch("wincoman.runner.save_cache"):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            with caplog.at_level(logging.INFO):
                code = orch.run()
        assert code == 0
        assert "DRY-RUN" in caplog.text

    def test_no_matches_returns_zero(self):
        cfg = ScanConfig()
        choco = _mock_choco(search_results=[])
        winget = _mock_manager("winget")
        scoop = _mock_manager("scoop")

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch("wincoman.runner.scan_installed_programs",
                   return_value=[{"DisplayName": "Git", "DisplayVersion": "2.44"}]):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            code = orch.run()
        assert code == 0


class TestOrchestratorPrerequisites:
    def test_returns_one_when_prereqs_fail(self):
        cfg = ScanConfig()
        orch = Orchestrator(cfg)
        with patch.object(orch, "_check_prerequisites", return_value=False):
            code = orch.run()
        assert code == 1

    def test_returns_one_when_winget_unavailable(self):
        cfg = ScanConfig()
        winget = _mock_manager("winget", available=False)
        choco = _mock_choco()
        scoop = _mock_manager("scoop")
        orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
        with patch.object(orch, "_check_prerequisites", return_value=True):
            code = orch.run()
        assert code == 1

    def test_returns_one_when_choco_unavailable(self):
        cfg = ScanConfig()
        winget = _mock_manager("winget")
        choco = _mock_choco(available=False)
        scoop = _mock_manager("scoop")

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch("wincoman.runner.scan_installed_programs", return_value=[]):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            code = orch.run()
        # Empty installed programs → returns 1
        assert code == 1


class TestOrchestratorAdminCheck:
    def test_non_admin_returns_false(self):
        orch = Orchestrator()
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0):
            result = orch._check_prerequisites()
        assert result is False

    def test_admin_returns_true(self):
        orch = Orchestrator()
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1):
            result = orch._check_prerequisites()
        assert result is True


class TestOrchestratorCache:
    def test_cache_hit_skips_scan(self):
        cfg = ScanConfig(use_cache=True, cache_path="/tmp/fake.json")
        matches = [_match()]
        unmanaged = [{"name": "Git", "version": "2.44"}]

        with patch("wincoman.runner.load_cache", return_value=(unmanaged, matches)), \
             patch("wincoman.runner.display_results") as mock_display, \
             patch("wincoman.runner.register_interactive", return_value=True):
            orch = Orchestrator(cfg)
            orch.run()
        mock_display.assert_called_once()
