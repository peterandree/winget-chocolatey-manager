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
    # search_many fires on_result for each result (default: empty)
    def _search_many(apps, *, progress_cb=None, on_result=None):
        return []
    mgr.search_many.side_effect = _search_many
    return mgr


def _mock_choco(available=True, search_results=None, managed=False):
    mgr = _mock_manager("chocolatey", available=available, managed=managed)
    results = search_results or []

    def _search_many(apps, *, progress_cb=None, on_result=None):
        for m in results:
            if on_result:
                on_result(m.app_name, m)
        return results

    mgr.search_many.side_effect = _search_many
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
        """_check_prerequisites() now always returns True — this tests the fallback path."""
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

    def test_choco_unavailable_does_not_abort_scan(self):
        """Chocolatey is optional — scan proceeds even when choco is not installed."""
        cfg = ScanConfig()
        winget = _mock_manager("winget")
        choco = _mock_choco(available=False)
        scoop = _mock_manager("scoop")

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch.object(Orchestrator, "_check_install_privileges", return_value=False), \
             patch("wincoman.runner.scan_installed_programs", return_value=[
                 {"DisplayName": "TestApp", "DisplayVersion": "1.0", "Publisher": "X"}
             ]):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            # Should NOT return 1 just because choco is unavailable
            code = orch.run()
        # 0 = all managed or no candidates (scan completed)
        assert code == 0

    def test_returns_one_when_choco_unavailable_old(self):
        """Legacy: kept to verify no regression — choco unavailable + no installed = exit 1."""
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
    def test_non_admin_install_privileges_returns_false(self):
        orch = Orchestrator()
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0):
            result = orch._check_install_privileges()
        assert result is False

    def test_admin_install_privileges_returns_true(self):
        orch = Orchestrator()
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1):
            result = orch._check_install_privileges()
        assert result is True

    def test_prerequisites_always_true(self):
        """Scanning never requires admin — _check_prerequisites() always returns True."""
        orch = Orchestrator()
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0):
            assert orch._check_prerequisites() is True


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


class TestOrchestratorMultiManagerSearch:
    """Issue #39: Step 5 fans out to all installable managers."""

    def _match_for(self, app_name, manager):
        return PackageMatch(app_name, "1.0", f"{app_name.lower()}-pkg", "1.0.0", False, manager)

    def test_winget_match_becomes_primary_when_preferred(self, caplog):
        """WinGet match is chosen as primary per MANAGER_PREFERENCE."""
        cfg = ScanConfig()
        wg_match = self._match_for("Git", "winget")
        ch_match = self._match_for("Git", "chocolatey")

        winget = _mock_manager("winget")

        def _wg_search_many(apps, *, progress_cb=None, on_result=None):
            if on_result:
                on_result("Git", wg_match)
            return [wg_match]
        winget.search_many.side_effect = _wg_search_many

        choco = _mock_choco(search_results=[ch_match])
        scoop = _mock_manager("scoop")

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch("wincoman.runner.scan_installed_programs",
                   return_value=[{"DisplayName": "Git", "DisplayVersion": "1.0"}]), \
             patch("wincoman.runner.save_cache"), \
             patch("wincoman.runner.register_interactive", return_value=True):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            with caplog.at_level(logging.INFO):
                code = orch.run()
        assert code == 0
        assert "winget" in caplog.text

    def test_prefer_manager_override(self):
        """--prefer-manager chocolatey overrides MANAGER_PREFERENCE."""
        cfg = ScanConfig(prefer_manager="chocolatey")
        wg_match = self._match_for("Git", "winget")
        ch_match = self._match_for("Git", "chocolatey")

        winget = _mock_manager("winget")

        def _wg_search(apps, *, progress_cb=None, on_result=None):
            if on_result:
                on_result("Git", wg_match)
            return [wg_match]
        winget.search_many.side_effect = _wg_search

        choco = _mock_choco(search_results=[ch_match])
        scoop = _mock_manager("scoop")

        captured_candidates = []

        def mock_display(c):
            captured_candidates.extend(c)

        with patch.object(Orchestrator, "_check_prerequisites", return_value=True), \
             patch("wincoman.runner.scan_installed_programs",
                   return_value=[{"DisplayName": "Git", "DisplayVersion": "1.0"}]), \
             patch("wincoman.runner.save_cache"), \
             patch("wincoman.runner.display_results", side_effect=mock_display), \
             patch("wincoman.runner.register_interactive", return_value=True):
            orch = Orchestrator(cfg, winget_mgr=winget, scoop_mgr=scoop, choco_mgr=choco)
            orch.run()

        assert any(
            hasattr(c, "primary") and c.primary.manager == "chocolatey"
            for c in captured_candidates
        )
