"""Tests for src/wincoman/matchers/base.py (Issues #22, #38, #39)."""
import pytest

from wincoman.matchers.base import (
    AppCandidates,
    BasePackageManager,
    InstallablePackageManager,
    PackageMatch,
    SearchablePackageManager,
    rank_candidates,
)


# ---------------------------------------------------------------------------
# PackageMatch
# ---------------------------------------------------------------------------


class TestPackageMatch:
    def test_is_frozen(self):
        m = PackageMatch(
            app_name="Git",
            app_version="2.44",
            pkg_id="git",
            pkg_version="2.44.0",
            version_mismatch=False,
            manager="chocolatey",
        )
        with pytest.raises((AttributeError, TypeError)):
            m.app_name = "other"  # type: ignore[misc]

    def test_fields_accessible(self):
        m = PackageMatch("A", "1.0", "a-pkg", "1.0.0", False, "winget")
        assert m.app_name == "A"
        assert m.manager == "winget"
        assert m.version_mismatch is False


# ---------------------------------------------------------------------------
# ABC enforcement — missing abstract methods raise TypeError on instantiation
# ---------------------------------------------------------------------------


class TestBasePackageManagerABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BasePackageManager()  # type: ignore[abstract]

    def test_missing_name_raises(self):
        class Incomplete(BasePackageManager):
            def is_available(self):
                return True

            def list_managed(self):
                return set()

            def is_managed(self, display_name):
                return False

        # 'name' property is abstract — must raise
        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_missing_is_available_raises(self):
        class Incomplete(BasePackageManager):
            @property
            def name(self):
                return "test"

            def list_managed(self):
                return set()

            def is_managed(self, display_name):
                return False

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_missing_list_managed_raises(self):
        class Incomplete(BasePackageManager):
            @property
            def name(self):
                return "test"

            def is_available(self):
                return True

            def is_managed(self, display_name):
                return False

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_missing_is_managed_raises(self):
        class Incomplete(BasePackageManager):
            @property
            def name(self):
                return "test"

            def is_available(self):
                return True

            def list_managed(self):
                return set()

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_complete_subclass_instantiates(self):
        class Complete(BasePackageManager):
            @property
            def name(self):
                return "test"

            def is_available(self):
                return True

            def list_managed(self):
                return set()

            def is_managed(self, display_name):
                return False

        obj = Complete()
        assert obj.name == "test"
        assert obj.is_available() is True


# ---------------------------------------------------------------------------
# SearchablePackageManager ABC
# ---------------------------------------------------------------------------


class TestSearchablePackageManagerABC:
    def test_cannot_instantiate_without_search(self):
        class NoSearch(SearchablePackageManager):
            @property
            def name(self):
                return "test"

            def is_available(self):
                return True

            def list_managed(self):
                return set()

            def is_managed(self, display_name):
                return False

            def search_many(self, apps, *, progress_cb=None):
                return []

        with pytest.raises(TypeError):
            NoSearch()  # type: ignore[abstract]

    def test_cannot_instantiate_without_search_many(self):
        class NoSearchMany(SearchablePackageManager):
            @property
            def name(self):
                return "test"

            def is_available(self):
                return True

            def list_managed(self):
                return set()

            def is_managed(self, display_name):
                return False

            def search(self, app_name):
                return None

        with pytest.raises(TypeError):
            NoSearchMany()  # type: ignore[abstract]

    def test_complete_searchable_subclass_instantiates(self):
        class Complete(SearchablePackageManager):
            @property
            def name(self):
                return "test"

            def is_available(self):
                return True

            def list_managed(self):
                return set()

            def is_managed(self, display_name):
                return False

            def search(self, app_name):
                return None

            def search_many(self, apps, *, progress_cb=None):
                return []

        obj = Complete()
        assert obj.name == "test"


# ---------------------------------------------------------------------------
# Importable from wincoman.matchers
# ---------------------------------------------------------------------------


class TestMatchers__init__:
    def test_importable_from_package(self):
        from wincoman.matchers import (
            BasePackageManager,
            PackageMatch,
            SearchablePackageManager,
        )

        assert BasePackageManager is not None
        assert PackageMatch is not None
        assert SearchablePackageManager is not None


# ---------------------------------------------------------------------------
# AppCandidates (Issue #38/#39)
# ---------------------------------------------------------------------------


def _pm(pkg_id, manager="winget"):
    return PackageMatch("Git", "2.44", pkg_id, "2.44.0", False, manager)


class TestAppCandidates:
    def test_all_matches_primary_only(self):
        cand = AppCandidates("Git", "2.44", primary=_pm("Git.Git"))
        assert cand.all_matches == [_pm("Git.Git")]

    def test_all_matches_with_alternatives(self):
        cand = AppCandidates(
            "Git", "2.44",
            primary=_pm("Git.Git"),
            alternatives=[_pm("git", "chocolatey")],
        )
        assert len(cand.all_matches) == 2
        assert cand.all_matches[0].manager == "winget"
        assert cand.all_matches[1].manager == "chocolatey"

    def test_is_frozen(self):
        cand = AppCandidates("Git", "2.44", primary=_pm("Git.Git"))
        with pytest.raises((AttributeError, TypeError)):
            cand.app_name = "Other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InstallablePackageManager ABC (Issue #38)
# ---------------------------------------------------------------------------


class TestInstallablePackageManagerABC:
    def test_cannot_instantiate_without_install(self):
        class NoInstall(InstallablePackageManager):
            @property
            def name(self):
                return "test"
            def is_available(self):
                return True
            def list_managed(self):
                return set()
            def is_managed(self, display_name):
                return False
            def search(self, app_name):
                return None
            def search_many(self, apps, *, progress_cb=None, on_result=None):
                return []

        with pytest.raises(TypeError):
            NoInstall()  # type: ignore[abstract]

    def test_complete_installable_subclass_instantiates(self):
        class Complete(InstallablePackageManager):
            @property
            def name(self):
                return "test"
            def is_available(self):
                return True
            def list_managed(self):
                return set()
            def is_managed(self, display_name):
                return False
            def search(self, app_name):
                return None
            def search_many(self, apps, *, progress_cb=None, on_result=None):
                return []
            def install(self, match, *, dry_run=False):
                return True

        obj = Complete()
        assert obj.name == "test"


# ---------------------------------------------------------------------------
# rank_candidates (Issue #39)
# ---------------------------------------------------------------------------


class TestRankCandidates:
    def _pm(self, app, pkg_id, manager):
        return PackageMatch(app, "1.0", pkg_id, "1.0.0", False, manager)

    def test_single_manager_match(self):
        results = {"Git": [self._pm("Git", "git", "chocolatey")]}
        candidates = rank_candidates(results, ["winget", "chocolatey"])
        assert len(candidates) == 1
        assert candidates[0].primary.manager == "chocolatey"
        assert candidates[0].alternatives == []

    def test_preference_order_picks_winget_first(self):
        results = {
            "Git": [
                self._pm("Git", "git", "chocolatey"),
                self._pm("Git", "Git.Git", "winget"),
            ]
        }
        candidates = rank_candidates(results, ["winget", "chocolatey"])
        assert candidates[0].primary.manager == "winget"
        assert len(candidates[0].alternatives) == 1
        assert candidates[0].alternatives[0].manager == "chocolatey"

    def test_prefer_override_moves_to_front(self):
        results = {
            "Git": [
                self._pm("Git", "git", "chocolatey"),
                self._pm("Git", "Git.Git", "winget"),
            ]
        }
        candidates = rank_candidates(results, ["winget", "chocolatey"], prefer_override="chocolatey")
        assert candidates[0].primary.manager == "chocolatey"

    def test_apps_with_no_match_excluded(self):
        results = {"Git": [self._pm("Git", "git", "chocolatey")], "UnknownApp": []}
        candidates = rank_candidates(results, ["winget", "chocolatey"])
        names = [c.app_name for c in candidates]
        assert "Git" in names
        assert "UnknownApp" not in names

    def test_multiple_apps_ranked_independently(self):
        results = {
            "Git": [self._pm("Git", "Git.Git", "winget")],
            "VLC": [self._pm("VLC", "vlc", "chocolatey")],
        }
        candidates = rank_candidates(results, ["winget", "chocolatey"])
        assert len(candidates) == 2

    def test_alternatives_sorted_by_preference(self):
        results = {
            "App": [
                self._pm("App", "app-scoop", "scoop"),
                self._pm("App", "App.App", "winget"),
                self._pm("App", "app-choco", "chocolatey"),
            ]
        }
        candidates = rank_candidates(results, ["winget", "chocolatey", "scoop"])
        assert candidates[0].primary.manager == "winget"
        assert candidates[0].alternatives[0].manager == "chocolatey"
        assert candidates[0].alternatives[1].manager == "scoop"
