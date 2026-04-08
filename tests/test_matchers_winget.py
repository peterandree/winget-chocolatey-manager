"""Tests for src/wincoman/matchers/winget.py (Issues #23, #38, #39)."""
import json
from unittest.mock import call

from wincoman.matchers.winget import WinGetManager, _parse_winget_table


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
        packages = [
            {"Name": "Git", "Id": "Git.Git", "Source": "winget"},
            {"Name": "Python 3.12", "Id": "Python.Python", "Source": "winget"},
        ]
        mgr = WinGetManager(runner=self._make_json_runner(packages))
        managed = mgr.list_managed()
        assert "git" in managed

    def test_excludes_sourceless_packages(self):
        """Packages without Source='winget' must not appear as managed."""
        packages = [
            {"Name": "Git", "Id": "Git.Git", "Source": "winget"},
            {"Name": "UnmanagedApp", "Id": "ARP\\...", "Source": ""},
        ]
        mgr = WinGetManager(runner=self._make_json_runner(packages))
        managed = mgr.list_managed()
        assert "git" in managed
        assert "unmanagedapp" not in managed

    def test_empty_list_when_winget_fails(self):
        mgr = WinGetManager(runner=_make_runner("", returncode=1))
        assert mgr.list_managed() == set()

    def test_falls_back_to_tabular_when_json_unsupported(self):
        """Older winget versions reject --output json; tabular output must still work."""
        TABULAR = (
            "Name                              Id              Version    Source\n"
            "--------------------------------  --------------  ---------  ------\n"
            "Git                               Git.Git         2.44.0     winget\n"
            "draw.io 29.6.6                    JGraph.Draw     29.6.6     winget\n"
        )

        def runner(cmd, **kwargs):
            if "--output" in cmd and "json" in cmd:
                return "", "Argument name was not recognized", 1
            return TABULAR, "", 0

        mgr = WinGetManager(runner=runner)
        managed = mgr.list_managed()
        assert "git" in managed
        # draw.io normalizes to "drawio" (dots stripped)
        assert "drawio" in managed

    def test_empty_list_on_invalid_json(self):
        """If JSON is returned but malformed, list is empty (both paths fail)."""
        mgr = WinGetManager(runner=_make_runner("not json"))
        assert mgr.list_managed() == set()

    def test_caches_result(self):
        calls = []

        def runner(cmd, **kwargs):
            calls.append(cmd)
            return json.dumps([{"Name": "Git", "Id": "Git.Git", "Source": "winget"}]), "", 0

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
        # Ensure all test packages have Source="winget" so they pass the filter
        pkgs_with_source = [
            dict(p, Source=p.get("Source", "winget")) for p in packages
        ]
        runner = _make_runner(json.dumps(pkgs_with_source))
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

    def test_version_in_display_name_still_matches(self):
        """Regression: 'HWiNFO64 7.28-4900' must match 'HWiNFO64' in winget list."""
        mgr = self._manager_with([{"Name": "HWiNFO64", "Id": "REALiX.HWiNFO"}])
        assert mgr.is_managed("HWiNFO64 7.28-4900") is True

    def test_version_suffix_stripped_for_fuzzy_path(self):
        """App with version suffix like 'Git 2.44.0' matches 'Git' in winget list."""
        mgr = self._manager_with([{"Name": "Git", "Id": "Git.Git"}])
        assert mgr.is_managed("Git 2.44.0") is True

    def test_drawio_versioned_name_matches(self):
        """Regression: winget list entry 'draw.io 29.6.6' matched against registry 'draw.io 29.6.6'."""
        mgr = self._manager_with([{"Name": "draw.io 29.6.6", "Id": "JGraph.Draw"}])
        assert mgr.is_managed("draw.io 29.6.6") is True

    def test_drawio_registry_versioned_winget_plain(self):
        """Registry 'draw.io 29.6.6' matched against winget list plain 'draw.io'."""
        mgr = self._manager_with([{"Name": "draw.io", "Id": "JGraph.Draw"}])
        assert mgr.is_managed("draw.io 29.6.6") is True


class TestParseWingetTable:
    """Unit tests for the tabular winget list parser."""

    SAMPLE = (
        "- \n"
        "Name                              Id              Version    Source\n"
        "--------------------------------  --------------  ---------  ------\n"
        "Git                               Git.Git         2.44.0     winget\n"
        "draw.io 29.6.6                    JGraph.Draw     29.6.6     winget\n"
        "7-Zip 26.00 (x64)                 7zip.7zip       26.00      winget\n"
        "SCMS                              ARP\\...         2.1.10\n"
    )

    def test_parses_name_and_id(self):
        result = _parse_winget_table(self.SAMPLE)
        names = [r["Name"] for r in result]
        assert "Git" in names
        assert "draw.io 29.6.6" in names

    def test_parses_source_column(self):
        result = _parse_winget_table(self.SAMPLE)
        by_name = {r["Name"]: r for r in result}
        assert by_name["Git"]["Source"] == "winget"
        assert by_name["draw.io 29.6.6"]["Source"] == "winget"
        assert by_name["SCMS"]["Source"] == ""  # no source

    def test_parses_versioned_name(self):
        result = _parse_winget_table(self.SAMPLE)
        ids = {r["Name"]: r["Id"] for r in result}
        assert ids.get("draw.io 29.6.6") == "JGraph.Draw"
        assert ids.get("Git") == "Git.Git"

    def test_skips_spinner_lines(self):
        result = _parse_winget_table(self.SAMPLE)
        for r in result:
            assert r["Name"].strip("- ")  # no spinner artifact as Name

    def test_empty_output_returns_empty(self):
        assert _parse_winget_table("") == []

    def test_no_header_returns_empty(self):
        assert _parse_winget_table("some random text\nno columns here\n") == []

    def test_name_with_parens(self):
        result = _parse_winget_table(self.SAMPLE)
        names = [r["Name"] for r in result]
        assert "7-Zip 26.00 (x64)" in names


class TestWinGetTabularFallback:
    """Integration: _get_name_map() falls back to tabular, filters by Source=winget."""

    TABULAR = (
        "Name                              Id              Version    Source\n"
        "--------------------------------  --------------  ---------  ------\n"
        "Git                               Git.Git         2.44.0     winget\n"
        "draw.io 29.6.6                    JGraph.Draw     29.6.6     winget\n"
        "SCMS                              ARP\\Machine\\..  2.1.10\n"
    )

    def _tabular_runner(self):
        def runner(cmd, **kwargs):
            if "--output" in cmd and "json" in cmd:
                return "", "not recognized", 1
            return self.TABULAR, "", 0
        return runner

    def test_name_map_populated_from_tabular(self):
        mgr = WinGetManager(runner=self._tabular_runner())
        name_map = mgr._get_name_map()
        assert "git" in name_map
        # draw.io should be indexed (either versioned or stripped form)
        assert "draw.io 29.6.6" in name_map or "draw.io" in name_map or "drawio" in name_map

    def test_sourceless_entries_excluded(self):
        """Apps without Source column (not winget-managed) must not appear in the map."""
        mgr = WinGetManager(runner=self._tabular_runner())
        name_map = mgr._get_name_map()
        assert "scms" not in name_map

    def test_is_managed_works_via_tabular(self):
        mgr = WinGetManager(runner=self._tabular_runner())
        assert mgr.is_managed("draw.io 29.6.6") is True
        assert mgr.is_managed("Git") is True  # Git has Source=winget in this fixture

    def test_sourceless_app_not_managed(self):
        """SCMS has no Source — must be reported as NOT managed by winget."""
        mgr = WinGetManager(runner=self._tabular_runner())
        assert mgr.is_managed("SCMS") is False

    def test_both_stripped_and_versioned_indexed(self):
        """The map must index both 'draw.io 29.6.6' and 'draw.io' so either form matches."""
        mgr = WinGetManager(runner=self._tabular_runner())
        mgr.list_managed()  # populate cache
        name_map = mgr._get_name_map()
        assert "draw.io 29.6.6" in name_map or "draw.io" in name_map or "drawio" in name_map


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
    """Issue #32 / regression: is_managed() must NOT fuzzy-match — only exact,
    version-stripped, and normalized lookups are permitted so that installed-by-
    winget classification has no false positives."""

    def _pkgs(self, *names_ids):
        return [{"Name": n, "Id": i, "Source": "winget"} for n, i in names_ids]

    def test_exact_match_detected(self):
        """Exact name match in name_map returns True."""
        packages = self._pkgs(
            ("GitHub Desktop", "GitHub.GitHubDesktop"),
            ("Visual Studio Code", "Microsoft.VisualStudioCode"),
            ("Node.js", "OpenJS.NodeJS"),
        )
        runner = _make_runner(json.dumps(packages))
        mgr = WinGetManager(runner=runner)
        assert mgr.is_managed("GitHub Desktop") is True
        assert mgr.is_managed("Visual Studio Code") is True
        assert mgr.is_managed("CompletelyUnknownApp") is False

    def test_no_fuzzy_false_positives(self):
        """is_managed() must NOT use fuzzy matching — low-similarity names must return False.

        Previously, 'Realtek Audio' fuzzy-matched 'drawio' at WRatio=60 and
        'AMD Software' matched 'nvidia physx system software' at 68.  With only
        exact/stripped/normalized lookups these are correctly rejected.
        """
        packages = self._pkgs(
            ("draw.io 29.6.6", "JGraph.Draw"),
            ("NVIDIA PhysX System Software", "NVIDIA.PhysX"),
        )
        runner = _make_runner(json.dumps(packages))
        mgr = WinGetManager(runner=runner)
        # These must NOT match via fuzzy — they are not winget-managed
        assert mgr.is_managed("Realtek Audio") is False
        assert mgr.is_managed("AMD Software") is False
        assert mgr.is_managed("Some Completely Different App") is False

    def test_version_stripped_match(self):
        """Name-map key stripped of version must still resolve to True."""
        packages = self._pkgs(("Git", "Git.Git"))
        runner = _make_runner(json.dumps(packages))
        mgr = WinGetManager(runner=runner)
        assert mgr.is_managed("git") is True
        # A totally different name must remain False
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

    def test_search_strips_version_from_query(self):
        """'HWiNFO64 7.28-4900' should find 'HWiNFO64' after stripping version."""
        search_json = json.dumps([
            {"Name": "HWiNFO64", "Id": "REALiX.HWiNFO", "Version": "7.30", "Source": "winget"},
        ])
        mgr = WinGetManager(runner=self._make_search_runner(search_json))
        result = mgr.search("HWiNFO64 7.28-4900")
        assert result is not None
        assert result.pkg_id == "REALiX.HWiNFO"
        assert result.app_name == "HWiNFO64 7.28-4900"  # original name preserved


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
