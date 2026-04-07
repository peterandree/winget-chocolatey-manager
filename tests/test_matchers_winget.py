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


class TestWinGetIsAvailableCaching:
    """Issue #34: is_available() should spawn subprocess at most once."""

    def test_is_available_cached_after_first_call(self):
        call_count = 0

        def counting_runner(cmd, **kwargs):
            nonlocal call_count
            if "--version" in cmd:
                call_count += 1
            return "v1.6", "", 0

        mgr = WinGetManager(runner=counting_runner)
        mgr.is_available()
        mgr.is_available()
        mgr.is_available()
        assert call_count == 1


class TestWinGetExtractOne:
    """Issue #32: is_managed() should use rapidfuzz.process.extractOne."""

    def test_fuzzy_match_uses_extract_one(self):
        """extractOne short-circuits — semantically identical to the loop."""
        packages = [
            {"Name": "GitHub Desktop", "Id": "GitHub.GitHubDesktop"},
            {"Name": "Visual Studio Code", "Id": "Microsoft.VisualStudioCode"},
            {"Name": "Node.js", "Id": "OpenJS.NodeJS"},
        ]
        runner = _make_runner(json.dumps(packages))
        mgr = WinGetManager(runner=runner)
        assert mgr.is_managed("GitHub Desktop") is True
        assert mgr.is_managed("Visual Studio Code") is True
        assert mgr.is_managed("CompletelyUnknownApp") is False

    def test_extract_one_respects_min_score(self):
        """Score cutoff is passed through to extractOne."""
        packages = [{"Name": "Git", "Id": "Git.Git"}]
        runner = _make_runner(json.dumps(packages))
        mgr = WinGetManager(runner=runner, min_score=99)
        # "Git" exact match still works (O(1) dict lookup)
        assert mgr.is_managed("git") is True
        # Fuzzy path: score("GitX", "git") < 99
        assert mgr.is_managed("GitXYZ") is False


# ──────────────────────────────────────────────────────────────────────────────
# Issue #38: WinGet is now an InstallablePackageManager
# ──────────────────────────────────────────────────────────────────────────────

WINGET_SEARCH_JSON = json.dumps([
    {"Name": "Git", "Id": "Git.Git", "Version": "2.44.0", "Source": "winget"},
    {"Name": "GitHub Desktop", "Id": "GitHub.GitHubDesktop", "Version": "3.3.0", "Source": "winget"},
])


class TestWinGetManagerSearch:
    def _make_search_runner(self, stdout, returncode=0):
        def runner(cmd, **kwargs):
            if "list" in cmd:
                return "[]", "", 0
            return stdout, "", returncode
        return runner

    def test_search_returns_match_for_known_app(self):
        mgr = WinGetManager(runner=self._make_search_runner(WINGET_SEARCH_JSON))
        result = mgr.search("Git")
        assert result is not None
        assert result.pkg_id == "Git.Git"
        assert result.manager == "winget"

    def test_search_returns_none_on_empty_results(self):
        mgr = WinGetManager(runner=self._make_search_runner("[]"))
        result = mgr.search("UnknownApp12345xyz")
        assert result is None

    def test_search_returns_none_on_winget_failure(self):
        mgr = WinGetManager(runner=self._make_search_runner("", returncode=1))
        result = mgr.search("Git")
        assert result is None

    def test_search_returns_none_on_invalid_json(self):
        mgr = WinGetManager(runner=self._make_search_runner("not json"))
        result = mgr.search("Git")
        assert result is None

    def test_search_respects_min_score(self):
        mgr = WinGetManager(
            runner=self._make_search_runner(WINGET_SEARCH_JSON),
            min_score=99,
        )
        # "Git" vs "Git" should score 100, so it should still match at min_score=99
        result = mgr.search("Git")
        assert result is not None
        # "XYZ" should not match anything
        result2 = mgr.search("XYZUnknownApp")
        assert result2 is None

    def test_search_returns_best_fuzzy_candidate(self):
        mgr = WinGetManager(runner=self._make_search_runner(WINGET_SEARCH_JSON))
        result = mgr.search("GitHub Desktop")
        assert result is not None
        assert result.pkg_id == "GitHub.GitHubDesktop"


class TestWinGetManagerSearchMany:
    def _manager(self, search_json="[]"):
        def runner(cmd, **kwargs):
            if "list" in cmd:
                return "[]", "", 0
            return search_json, "", 0
        return WinGetManager(runner=runner, search_workers=2)

    def test_returns_list_of_matches(self):
        mgr = self._manager(WINGET_SEARCH_JSON)
        apps = [{"name": "Git", "version": "2.44.0"}]
        results = mgr.search_many(apps)
        assert len(results) == 1
        assert results[0].pkg_id == "Git.Git"

    def test_on_result_callback_fires(self):
        received = []
        mgr = self._manager(WINGET_SEARCH_JSON)
        apps = [{"name": "Git", "version": ""}]
        mgr.search_many(apps, on_result=lambda n, m: received.append((n, m)))
        assert len(received) == 1
        name, match = received[0]
        assert name == "Git"
        assert match is not None

    def test_on_result_none_when_no_match(self):
        received = []
        mgr = self._manager("[]")
        apps = [{"name": "UnknownApp", "version": ""}]
        mgr.search_many(apps, on_result=lambda n, m: received.append((n, m)))
        assert received[0][1] is None


class TestWinGetManagerInstall:
    def test_install_success(self):
        def runner(cmd, **kwargs):
            assert "--id" in cmd
            assert "--exact" in cmd
            assert "--silent" in cmd
            return "", "", 0
        mgr = WinGetManager(runner=runner)
        from wincoman.matchers.base import PackageMatch
        match = PackageMatch("Git", "2.44", "Git.Git", "2.44.0", False, "winget")
        assert mgr.install(match) is True

    def test_install_failure(self):
        def runner(cmd, **kwargs):
            return "", "install failed", 1
        mgr = WinGetManager(runner=runner)
        from wincoman.matchers.base import PackageMatch
        match = PackageMatch("Git", "2.44", "Git.Git", "2.44.0", False, "winget")
        assert mgr.install(match) is False

    def test_install_dry_run(self, caplog):
        import logging
        called = []
        def runner(cmd, **kwargs):
            called.append(cmd)
            return "", "", 0
        mgr = WinGetManager(runner=runner)
        from wincoman.matchers.base import PackageMatch
        match = PackageMatch("Git", "2.44", "Git.Git", "2.44.0", False, "winget")
        with caplog.at_level(logging.INFO):
            result = mgr.install(match, dry_run=True)
        assert result is True
        # runner should NOT have been called with install
        install_calls = [c for c in called if "install" in c]
        assert len(install_calls) == 0
        assert "DRY-RUN" in caplog.text
