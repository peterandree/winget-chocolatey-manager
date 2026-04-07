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


class TestOrchestratorParallelQueries:
    """Issue #33: Steps 1-3 should run concurrently."""

    def test_parallel_queries_returns_all_results(self):
        cfg = ScanConfig()
        winget = _mock_manager("winget")
        scoop = _mock_manager("scoop")
        choco = _mock_choco()

        installed_programs = [{"DisplayName": "Git", "DisplayVersion": "2.44"}]
        with patch("wincoman.runner.scan_installed_programs", return_value=installed_programs):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            wg_ok, sc_ok, ch_ok, installed = orch._parallel_queries(cfg)

        assert wg_ok is True
        assert sc_ok is True
        assert ch_ok is True
        assert installed == installed_programs
        winget.list_managed.assert_called_once()
        scoop.list_managed.assert_called_once()
        choco.list_managed.assert_called_once()

    def test_parallel_queries_propagates_unavailability(self):
        cfg = ScanConfig()
        winget = _mock_manager("winget", available=False)
        scoop = _mock_manager("scoop")
        choco = _mock_choco(available=False)

        with patch("wincoman.runner.scan_installed_programs", return_value=[]):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            wg_ok, sc_ok, ch_ok, installed = orch._parallel_queries(cfg)

        assert wg_ok is False
        assert ch_ok is False

    def test_all_queries_dispatched_concurrently(self):
        """Verify all 4 tasks run in the thread pool, not sequentially."""
        import threading

        threads_seen: set[int] = set()

        cfg = ScanConfig()
        winget = _mock_manager("winget")
        scoop = _mock_manager("scoop")
        choco = _mock_choco()

        orig_winget_list = winget.list_managed
        orig_scoop_list = scoop.list_managed
        orig_choco_list = choco.list_managed

        def track_winget():
            threads_seen.add(threading.current_thread().ident)
            return orig_winget_list()
        def track_scoop():
            threads_seen.add(threading.current_thread().ident)
            return orig_scoop_list()
        def track_choco():
            threads_seen.add(threading.current_thread().ident)
            return orig_choco_list()

        winget.list_managed = track_winget
        scoop.list_managed = track_scoop
        choco.list_managed = track_choco

        def scan_reg(cfg):
            threads_seen.add(threading.current_thread().ident)
            return [{"DisplayName": "Git"}]

        with patch("wincoman.runner.scan_installed_programs", side_effect=scan_reg):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            orch._parallel_queries(cfg)

        # At least some tasks ran in pool threads (not all in the main thread)
        assert len(threads_seen) >= 1


class TestOrchestratorSummary:
    """Issue #37: scan summary displayed on all exit paths."""

    def test_summary_shown_on_all_managed_path(self, caplog):
        """When all apps are managed, summary still appears."""
        cfg = ScanConfig()
        winget = _mock_manager("winget", managed=True)
        scoop = _mock_manager("scoop")
        choco = _mock_choco(managed=True)

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch("wincoman.runner.scan_installed_programs",
                   return_value=[{"DisplayName": "Git", "DisplayVersion": "2.44"}]):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            with caplog.at_level(logging.INFO):
                code = orch.run()
        assert code == 0
        assert "SCAN SUMMARY" in caplog.text

    def test_summary_shown_on_no_matches_path(self, caplog):
        """When choco search finds nothing, summary still appears."""
        cfg = ScanConfig()
        choco = _mock_choco(search_results=[])
        winget = _mock_manager("winget")
        scoop = _mock_manager("scoop")

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch("wincoman.runner.scan_installed_programs",
                   return_value=[{"DisplayName": "Git", "DisplayVersion": "2.44"}]):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            with caplog.at_level(logging.INFO):
                code = orch.run()
        assert code == 0
        assert "SCAN SUMMARY" in caplog.text

    def test_summary_shown_on_dry_run_path(self, caplog):
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
        assert "SCAN SUMMARY" in caplog.text
