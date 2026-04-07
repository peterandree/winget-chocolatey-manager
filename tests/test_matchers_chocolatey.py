"""Tests for src/wincoman/matchers/chocolatey.py (Issue #24, #31)."""

from wincoman.config import ScanConfig
from wincoman.matchers.chocolatey import ChocolateyManager
from wincoman.matchers.base import PackageMatch


def _make_runner(stdout="", returncode=0, choco_version="2.3.0"):
    def runner(cmd, **kwargs):
        if cmd == ["choco", "--version"] and returncode == 0:
            return choco_version, "", 0
        return stdout, "", returncode

    return runner


CHOCO_LIST_V1 = "git|2.44.0\nnodejs|20.11.0\n"
CHOCO_SEARCH_EXACT = "git|2.44.0\n"
CHOCO_SEARCH_FUZZY = "github-desktop|3.3.0\ngit|2.44.0\n"


class TestChocolateyManagerAvailability:
    def test_available_when_choco_responds(self):
        mgr = ChocolateyManager(runner=_make_runner("2.3.0"))
        assert mgr.is_available() is True

    def test_unavailable_when_choco_missing(self):
        mgr = ChocolateyManager(runner=_make_runner("", returncode=1))
        assert mgr.is_available() is False

    def test_is_available_cached_after_first_call(self):
        """Issue #34: is_available() spawns subprocess at most once."""
        call_count = 0

        def counting_runner(cmd, **kwargs):
            nonlocal call_count
            if cmd == ["choco", "--version"]:
                call_count += 1
                return "2.3.0", "", 0
            return "", "", 0

        mgr = ChocolateyManager(runner=counting_runner)
        mgr.is_available()
        mgr.is_available()
        mgr.is_available()
        assert call_count == 1


class TestChocolateyManagerListManaged:
    def _manager(self, stdout, choco_major=1):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["choco", "--version"]:
                return f"{choco_major}.0.0", "", 0
            return stdout, "", 0

        mgr = ChocolateyManager(runner=runner)
        result = mgr.list_managed()
        return result, calls

    def test_parses_packages_v1(self):
        managed, _ = self._manager(CHOCO_LIST_V1, choco_major=1)
        assert "git" in managed

    def test_v1_uses_limit_output(self):
        _, calls = self._manager(CHOCO_LIST_V1, choco_major=1)
        assert any("--limit-output" in c for c in calls)

    def test_v2_omits_limit_output(self):
        _, calls = self._manager(CHOCO_LIST_V1, choco_major=2)
        assert not any("--limit-output" in c for c in calls)


class TestChocolateyManagerSearch:
    def _manager_with_search_results(self, search_stdout, choco_major=2, min_score=60):
        def runner(cmd, **kwargs):
            if cmd == ["choco", "--version"]:
                return f"{choco_major}.0.0", "", 0
            return search_stdout, "", 0

        config = ScanConfig(min_score=min_score)
        mgr = ChocolateyManager(config=config, runner=runner, sleep=lambda _: None)
        return mgr

    def test_exact_match_returns_package_match(self):
        mgr = self._manager_with_search_results(CHOCO_SEARCH_EXACT)
        result = mgr.search("git")
        assert result is not None
        assert isinstance(result, PackageMatch)
        assert result.pkg_id == "git"

    def test_no_result_returns_none(self):
        mgr = self._manager_with_search_results("", choco_major=2)
        # Empty search output — no match
        result = mgr.search("UnknownApp12345xyz")
        assert result is None

    def test_fuzzy_match_above_threshold_accepted(self):
        mgr = self._manager_with_search_results(CHOCO_SEARCH_FUZZY)
        result = mgr.search("GitHub Desktop")
        # "GitHub Desktop" should fuzzy-match "github-desktop" (score >= 60)
        assert result is not None

    def test_fuzzy_match_below_threshold_rejected(self):
        # Exact search returns nothing; fuzzy search returns results but score < threshold
        def runner(cmd, **kwargs):
            if cmd == ["choco", "--version"]:
                return "2.0.0", "", 0
            if "--exact" in cmd:
                return "", "", 0  # exact: no match
            return CHOCO_SEARCH_FUZZY, "", 0  # fuzzy: low-score candidates

        mgr = ChocolateyManager(
            config=ScanConfig(min_score=99),
            runner=runner,
            sleep=lambda _: None,
        )
        result = mgr.search("XYZTotallyDifferent")
        assert result is None


class TestChocolateyManagerSearchMany:
    def test_returns_list_of_matches(self):
        def runner(cmd, **kwargs):
            if cmd == ["choco", "--version"]:
                return "2.0.0", "", 0
            return CHOCO_SEARCH_EXACT, "", 0

        config = ScanConfig(min_score=60)
        mgr = ChocolateyManager(config=config, runner=runner, sleep=lambda _: None)

        apps = [{"name": "git", "version": "2.44.0"}]
        results = mgr.search_many(apps)
        assert len(results) == 1
        assert results[0].pkg_id == "git"

    def test_concurrent_search_dispatches_all_apps(self):
        """Issue #30: all apps are dispatched to the thread pool."""
        import threading

        search_threads: set[int] = set()

        def runner(cmd, **kwargs):
            if cmd == ["choco", "--version"]:
                return "2.0.0", "", 0
            search_threads.add(threading.current_thread().ident)
            return CHOCO_SEARCH_EXACT, "", 0

        config = ScanConfig(min_score=60, search_workers=3)
        mgr = ChocolateyManager(config=config, runner=runner, sleep=lambda _: None)

        apps = [
            {"name": "git", "version": ""},
            {"name": "nodejs", "version": ""},
            {"name": "python", "version": ""},
        ]
        results = mgr.search_many(apps)
        assert len(results) == 3
        # Searches ran in thread pool threads (may reuse threads, but at least 1)
        assert len(search_threads) >= 1

    def test_search_workers_limits_concurrency(self):
        """search_workers caps the thread pool size."""
        import threading

        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        def runner(cmd, **kwargs):
            nonlocal max_concurrent, current_concurrent
            if cmd == ["choco", "--version"]:
                return "2.0.0", "", 0
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            import time as _time
            _time.sleep(0.05)
            with lock:
                current_concurrent -= 1
            return CHOCO_SEARCH_EXACT, "", 0

        config = ScanConfig(min_score=60, search_workers=2)
        mgr = ChocolateyManager(config=config, runner=runner, sleep=lambda _: None)

        apps = [{"name": f"app{i}", "version": ""} for i in range(6)]
        mgr.search_many(apps)
        assert max_concurrent <= 2, f"Expected ≤2 concurrent, got {max_concurrent}"

    def test_progress_callback_called(self):
        progress = []

        def runner(cmd, **kwargs):
            if cmd == ["choco", "--version"]:
                return "2.0.0", "", 0
            return CHOCO_SEARCH_EXACT, "", 0

        mgr = ChocolateyManager(runner=runner, sleep=lambda _: None)

        apps = [{"name": "git", "version": ""}]
        mgr.search_many(apps, progress_cb=lambda i, t: progress.append((i, t)))
        assert (1, 1) in progress


class TestChocoMajorVersionCaching:
    """Issue #31: _choco_major_version() must be called at most once per instance."""

    def test_choco_version_called_once_across_multiple_searches(self):
        """Even after N search() calls, get_choco_major_version is invoked only once."""
        call_count = 0

        def counting_runner(cmd, **kwargs):
            nonlocal call_count
            if cmd == ["choco", "--version"]:
                call_count += 1
                return "2.3.0", "", 0
            return CHOCO_SEARCH_EXACT, "", 0

        mgr = ChocolateyManager(runner=counting_runner, sleep=lambda _: None)
        mgr.search("git")
        mgr.search("nodejs")
        mgr.search("python")
        assert call_count == 1, f"Expected 1 choco --version call, got {call_count}"

    def test_choco_version_cached_across_list_and_search(self):
        """Version is cached across list_managed() and search() calls."""
        call_count = 0

        def counting_runner(cmd, **kwargs):
            nonlocal call_count
            if cmd == ["choco", "--version"]:
                call_count += 1
                return "1.4.0", "", 0
            if "list" in cmd:
                return CHOCO_LIST_V1, "", 0
            return CHOCO_SEARCH_EXACT, "", 0

        mgr = ChocolateyManager(runner=counting_runner, sleep=lambda _: None)
        mgr.list_managed()
        mgr.search("git")
        assert call_count == 1
