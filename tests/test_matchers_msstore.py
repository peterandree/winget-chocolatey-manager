"""Tests for src/wincoman/matchers/msstore.py — Microsoft Store adapter."""
from __future__ import annotations

from wincoman.matchers.msstore import MicrosoftStoreManager


# Simulated Get-AppxPackage output (name|version)
APPX_OUTPUT = (
    "Microsoft.WindowsCalculator|11.2508.4.0\n"
    "Microsoft.ScreenSketch|11.2601.2.0\n"
    "Microsoft.YourPhone|1.26012.101.0\n"
    "NVIDIACorp.NVIDIAControlPanel|8.1.969.0\n"
    "Microsoft.AV1VideoExtension|2.0.7.0\n"
    "Microsoft.Windows.Photos|2026.11020.20001.0\n"
    "AD2F1837.HPDisplayCenter|2.5.3.0\n"
    "Microsoft.WindowsStore|22602.1401.6.0\n"
    "MicrosoftWindows.CrossDevice|1.26012.79.0\n"
)


def _make_runner(appx_stdout=APPX_OUTPUT, available=True):
    """Return a runner that fakes Get-AppxPackage output.

    With ``available=False`` the full Get-AppxPackage query returns exit code 1,
    making both ``is_available()`` and ``_get_name_map()`` treat the store as
    unavailable.
    """
    def runner(cmd, **kwargs):
        # Full list query (also used by is_available via _get_name_map)
        if not available:
            return "", "Get-AppxPackage not available", 1
        return appx_stdout, "", 0
    return runner


class TestMicrosoftStoreAvailability:
    def test_available_when_powershell_works(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_available() is True

    def test_unavailable_when_powershell_fails(self):
        mgr = MicrosoftStoreManager(runner=_make_runner(available=False))
        assert mgr.is_available() is False

    def test_cached_after_first_call(self):
        call_count = 0
        def runner(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return APPX_OUTPUT, "", 0
        mgr = MicrosoftStoreManager(runner=runner)
        mgr.is_available()
        mgr.is_available()
        # Only one PS call: the first is_available triggers _get_name_map, second is cached
        assert call_count == 1


class TestMicrosoftStoreListManaged:
    def test_finds_store_apps(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        managed = mgr.list_managed()
        # Raw name form
        assert "microsoft.windowscalculator" in managed
        # Normalised
        assert "microsoftwindowscalculator" in managed

    def test_empty_when_unavailable(self):
        mgr = MicrosoftStoreManager(runner=_make_runner("", available=True))
        # Empty output → no apps
        assert len(mgr.list_managed()) == 0


class TestMicrosoftStoreIsManaged:
    def test_exact_appx_name(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Microsoft.WindowsCalculator") is True

    def test_friendly_name_windows_calculator(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Windows Calculator") is True

    def test_friendly_name_snipping_tool(self):
        """Snipping Tool = Microsoft.ScreenSketch via alias."""
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Snipping Tool") is True

    def test_friendly_name_phone_link(self):
        """Phone Link = Microsoft.YourPhone via alias."""
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Phone Link") is True

    def test_friendly_name_microsoft_store(self):
        """Microsoft Store = Microsoft.WindowsStore via alias."""
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Microsoft Store") is True

    def test_friendly_name_microsoft_photos(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Microsoft Photos") is True

    def test_nvidia_control_panel(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("NVIDIA Control Panel") is True

    def test_hp_display_center(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("HP Display Center") is True

    def test_av1_video_extension(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("AV1 Video Extension") is True

    def test_cross_device_experience_host(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Cross Device Experience Host") is True

    def test_unmanaged_returns_false(self):
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("CompletelyRandomApp9999") is False

    def test_git_not_in_store(self):
        """Git is not a Store app — must return False."""
        mgr = MicrosoftStoreManager(runner=_make_runner())
        assert mgr.is_managed("Git") is False


class TestNameMapIndexing:
    def test_suffix_indexing(self):
        """Last dotted segment is indexed (e.g. 'NVIDIAControlPanel')."""
        mgr = MicrosoftStoreManager(runner=_make_runner())
        nm = mgr._get_name_map()
        assert "nvidiacontrolpanel" in nm

    def test_vendor_prefix_stripping(self):
        """Microsoft. prefix is stripped for an alternative key."""
        mgr = MicrosoftStoreManager(runner=_make_runner())
        nm = mgr._get_name_map()
        assert "windowscalculator" in nm
        assert "windows.photos" in nm
