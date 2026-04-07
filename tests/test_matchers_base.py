"""Tests for src/wincoman/matchers/base.py (Issue #22)."""
import pytest

from wincoman.matchers.base import (
    BasePackageManager,
    PackageMatch,
    SearchablePackageManager,
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
