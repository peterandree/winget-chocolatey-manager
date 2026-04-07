"""Tests for src/wincoman/matchers/chocolatey.py (Issue #24)."""
from unittest.mock import patch

from wincoman.config import ScanConfig
from wincoman.matchers.chocolatey import ChocolateyManager
from wincoman.matchers.base import PackageMatch


def _make_runner(stdout="", returncode=0):
    def runner(cmd, **kwargs):
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


class TestChocolateyManagerListManaged:
    def _manager(self, stdout, choco_major=1):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return stdout, "", 0

        with patch("wincoman.matchers.chocolatey.get_choco_major_version", return_value=choco_major):
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
            return search_stdout, "", 0

        config = ScanConfig(min_score=min_score)
        with patch("wincoman.matchers.chocolatey.get_choco_major_version", return_value=choco_major):
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
            if "--exact" in cmd:
                return "", "", 0  # exact: no match
            return CHOCO_SEARCH_FUZZY, "", 0  # fuzzy: low-score candidates

        with patch("wincoman.matchers.chocolatey.get_choco_major_version", return_value=2):
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
            return CHOCO_SEARCH_EXACT, "", 0

        config = ScanConfig(min_score=60)
        with patch("wincoman.matchers.chocolatey.get_choco_major_version", return_value=2):
            mgr = ChocolateyManager(config=config, runner=runner, sleep=lambda _: None)

        apps = [{"name": "git", "version": "2.44.0"}]
        results = mgr.search_many(apps)
        assert len(results) == 1
        assert results[0].pkg_id == "git"

    def test_sleep_called_between_searches(self):
        sleep_calls = []

        def runner(cmd, **kwargs):
            return CHOCO_SEARCH_EXACT, "", 0

        with patch("wincoman.matchers.chocolatey.get_choco_major_version", return_value=2):
            mgr = ChocolateyManager(
                runner=runner, sleep=lambda d: sleep_calls.append(d)
            )

        apps = [{"name": "git", "version": ""}, {"name": "nodejs", "version": ""}]
        mgr.search_many(apps)
        # sleep called once between the two searches (not after the last one)
        assert len(sleep_calls) == 1

    def test_progress_callback_called(self):
        progress = []

        def runner(cmd, **kwargs):
            return CHOCO_SEARCH_EXACT, "", 0

        with patch("wincoman.matchers.chocolatey.get_choco_major_version", return_value=2):
            mgr = ChocolateyManager(runner=runner, sleep=lambda _: None)

        apps = [{"name": "git", "version": ""}]
        mgr.search_many(apps, progress_cb=lambda i, t: progress.append((i, t)))
        assert (1, 1) in progress
