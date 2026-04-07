"""Tests for src/wincoman/detector.py (Issues #27, #35)."""
from wincoman.detector import find_unmanaged


class _AlwaysManaged:
    name = "always"

    def is_managed(self, display_name):
        return True


class _NeverManaged:
    name = "never"

    def is_managed(self, display_name):
        return False


class _ManagedIf:
    def __init__(self, mgr_name, app_name):
        self.name = mgr_name
        self._app = app_name.lower()

    def is_managed(self, display_name):
        return display_name.lower() == self._app


INSTALLED = [
    {"DisplayName": "Git", "DisplayVersion": "2.44", "Publisher": "Git"},
    {"DisplayName": "VLC", "DisplayVersion": "3.0", "Publisher": "VideoLAN"},
    {"DisplayName": "SomeApp", "DisplayVersion": "1.0", "Publisher": "Vendor"},
]


class TestFindUnmanaged:
    def test_returns_all_when_no_managers(self):
        result = find_unmanaged(INSTALLED, [])
        assert len(result) == len(INSTALLED)

    def test_returns_empty_when_all_managed(self):
        result = find_unmanaged(INSTALLED, [_AlwaysManaged()])
        assert result == []

    def test_returns_unmanaged_subset(self):
        # Only "git" is managed
        result = find_unmanaged(INSTALLED, [_ManagedIf("winget", "git")])
        names = [r["name"] for r in result]
        assert "Git" not in names
        assert "VLC" in names
        assert "SomeApp" in names

    def test_app_excluded_when_any_manager_claims_it(self):
        # Two managers: one claims VLC, one claims Git
        result = find_unmanaged(
            INSTALLED,
            [_ManagedIf("scoop", "vlc"), _ManagedIf("winget", "git")],
        )
        names = [r["name"] for r in result]
        assert "VLC" not in names
        assert "Git" not in names
        assert "SomeApp" in names

    def test_empty_installed_returns_empty(self):
        result = find_unmanaged([], [_AlwaysManaged()])
        assert result == []

    def test_all_managers_unavailable_returns_full_list(self):
        result = find_unmanaged(INSTALLED, [_NeverManaged(), _NeverManaged()])
        assert len(result) == len(INSTALLED)

    def test_result_has_expected_keys(self):
        result = find_unmanaged(INSTALLED, [])
        for item in result:
            assert "name" in item
            assert "version" in item
            assert "publisher" in item
            assert "normalized" in item

    def test_skips_entries_without_display_name(self):
        installed = [
            {"DisplayName": "", "DisplayVersion": "1.0"},
            {"DisplayVersion": "2.0"},  # no DisplayName key
            {"DisplayName": "RealApp", "DisplayVersion": "1.0"},
        ]
        result = find_unmanaged(installed, [])
        assert len(result) == 1
        assert result[0]["name"] == "RealApp"

    def test_does_not_mutate_input(self):
        installed = [{"DisplayName": "Git", "DisplayVersion": "2.44"}]
        original_len = len(installed)
        find_unmanaged(installed, [_AlwaysManaged()])
        assert len(installed) == original_len


class TestClassifyCallback:
    """Issue #35: on_classify callback receives (app_name, manager_name|None)."""

    def test_callback_receives_managed_apps_with_manager_name(self):
        classifications = []
        find_unmanaged(
            INSTALLED,
            [_ManagedIf("winget", "git")],
            on_classify=lambda name, mgr: classifications.append((name, mgr)),
        )
        assert ("Git", "winget") in classifications

    def test_callback_receives_unmanaged_apps_with_none(self):
        classifications = []
        find_unmanaged(
            INSTALLED,
            [_ManagedIf("winget", "git")],
            on_classify=lambda name, mgr: classifications.append((name, mgr)),
        )
        assert ("VLC", None) in classifications
        assert ("SomeApp", None) in classifications

    def test_callback_fires_for_every_app(self):
        classifications = []
        find_unmanaged(
            INSTALLED,
            [_ManagedIf("winget", "git")],
            on_classify=lambda name, mgr: classifications.append((name, mgr)),
        )
        assert len(classifications) == len(INSTALLED)

    def test_no_callback_is_backward_compatible(self):
        # No on_classify → no error
        result = find_unmanaged(INSTALLED, [_AlwaysManaged()])
        assert result == []

    def test_callback_identifies_correct_manager(self):
        """When multiple managers are tried, the first claiming one is reported."""
        classifications = []
        find_unmanaged(
            INSTALLED,
            [_ManagedIf("winget", "git"), _ManagedIf("chocolatey", "vlc")],
            on_classify=lambda name, mgr: classifications.append((name, mgr)),
        )
        assert ("Git", "winget") in classifications
        assert ("VLC", "chocolatey") in classifications
        assert ("SomeApp", None) in classifications
