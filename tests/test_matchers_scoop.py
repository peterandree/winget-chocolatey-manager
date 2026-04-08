"""Tests for src/wincoman/matchers/scoop.py (Issue #23)."""
from wincoman.matchers.scoop import ScoopManager, _strip_ansi


def _make_runner(stdout="", returncode=0):
    def runner(cmd, **kwargs):
        return stdout, "", returncode

    return runner


SCOOP_LIST_OUTPUT = (
    "Name      Version  Source  Updated              Info\n"
    "----      -------  ------  -------              ----\n"
    "git       2.44.0   main    2024-01-15 12:00:00\n"
    "nodejs    20.11.0  main    2024-01-10 09:00:00\n"
)

# Real scoop list output contains ANSI colour codes in header rows
SCOOP_LIST_ANSI = (
    "Installed apps:\n"
    "\n"
    "\x1b[32;1mName        \x1b[0m\x1b[32;1m Version\x1b[0m\x1b[32;1m Source\x1b[0m\n"
    "\x1b[32;1m----        \x1b[0m \x1b[32;1m-------\x1b[0m \x1b[32;1m------\x1b[0m\n"
    "scoop-search 2.1.0   main\n"
    "\n"
)


class TestScoopManagerAvailability:
    def test_available_when_scoop_responds(self):
        mgr = ScoopManager(runner=_make_runner("0.4.0"))
        assert mgr.is_available() is True

    def test_unavailable_when_scoop_missing(self):
        mgr = ScoopManager(runner=_make_runner("", returncode=1))
        assert mgr.is_available() is False


class TestScoopManagerListManaged:
    def test_parses_package_names(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        managed = mgr.list_managed()
        assert "git" in managed
        assert "nodejs" in managed

    def test_empty_when_scoop_not_found(self):
        mgr = ScoopManager(runner=_make_runner("", returncode=1))
        assert mgr.list_managed() == set()

    def test_excludes_header_row(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        managed = mgr.list_managed()
        assert "name" not in managed
        assert "----" not in managed

    def test_ansi_header_stripped_not_included(self):
        """Real scoop output has ANSI codes in headers — must not pollute the package set."""
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_ANSI))
        raw = mgr._raw_names()
        assert raw == {"scoop-search"}, f"Unexpected names: {raw}"

    def test_ansi_app_is_managed(self):
        """App on a plain data line is correctly detected as managed."""
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_ANSI))
        assert mgr.is_managed("scoop-search") is True


class TestStripAnsi:
    def test_removes_colour_codes(self):
        assert _strip_ansi("\x1b[32;1mName\x1b[0m") == "Name"

    def test_plain_text_unchanged(self):
        assert _strip_ansi("scoop-search") == "scoop-search"

    def test_empty_string(self):
        assert _strip_ansi("") == ""


class TestScoopManagerIsManaged:
    def test_managed_returns_true(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        assert mgr.is_managed("git") is True

    def test_unmanaged_returns_false(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        assert mgr.is_managed("unknown-app-xyz") is False


class TestScoopIsAvailableCaching:
    """Issue #34: is_available() should spawn subprocess at most once."""

    def test_is_available_cached_after_first_call(self):
        call_count = 0

        def counting_runner(cmd, **kwargs):
            nonlocal call_count
            if "--version" in cmd:
                call_count += 1
            return "0.4.0", "", 0

        mgr = ScoopManager(runner=counting_runner)
        mgr.is_available()
        mgr.is_available()
        mgr.is_available()
        assert call_count == 1


class TestScoopNormalisedSetCaching:
    """Issue #34: Scoop normalised name set should be built once, not per call."""

    def test_normalised_set_built_once(self):
        normalize_calls = []
        original_normalize = __import__("wincoman.scoring", fromlist=["normalize_name"]).normalize_name

        def counting_normalize(name):
            normalize_calls.append(name)
            return original_normalize(name)

        from unittest.mock import patch

        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        with patch("wincoman.matchers.scoop.normalize_name", side_effect=counting_normalize):
            mgr.is_managed("git")
            first_count = len(normalize_calls)
            mgr.is_managed("nodejs")
            second_count = len(normalize_calls)

        # Second call should add only 1 normalize call (for the display_name itself)
        # not rebuild the full set
        incremental = second_count - first_count
        assert incremental <= 1, f"Expected ≤1 normalize call, got {incremental}"


def _make_runner(stdout="", returncode=0):
    def runner(cmd, **kwargs):
        return stdout, "", returncode

    return runner


SCOOP_LIST_OUTPUT = (
    "Name      Version  Source  Updated              Info\n"
    "----      -------  ------  -------              ----\n"
    "git       2.44.0   main    2024-01-15 12:00:00\n"
    "nodejs    20.11.0  main    2024-01-10 09:00:00\n"
)


class TestScoopManagerAvailability:
    def test_available_when_scoop_responds(self):
        mgr = ScoopManager(runner=_make_runner("0.4.0"))
        assert mgr.is_available() is True

    def test_unavailable_when_scoop_missing(self):
        mgr = ScoopManager(runner=_make_runner("", returncode=1))
        assert mgr.is_available() is False


class TestScoopManagerListManaged:
    def test_parses_package_names(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        managed = mgr.list_managed()
        assert "git" in managed
        assert "nodejs" in managed

    def test_empty_when_scoop_not_found(self):
        mgr = ScoopManager(runner=_make_runner("", returncode=1))
        assert mgr.list_managed() == set()

    def test_excludes_header_row(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        managed = mgr.list_managed()
        assert "name" not in managed
        assert "----" not in managed


class TestScoopManagerIsManaged:
    def test_managed_returns_true(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        assert mgr.is_managed("git") is True

    def test_unmanaged_returns_false(self):
        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        assert mgr.is_managed("unknown-app-xyz") is False


class TestScoopIsAvailableCaching:
    """Issue #34: is_available() should spawn subprocess at most once."""

    def test_is_available_cached_after_first_call(self):
        call_count = 0

        def counting_runner(cmd, **kwargs):
            nonlocal call_count
            if "--version" in cmd:
                call_count += 1
            return "0.4.0", "", 0

        mgr = ScoopManager(runner=counting_runner)
        mgr.is_available()
        mgr.is_available()
        mgr.is_available()
        assert call_count == 1


class TestScoopNormalisedSetCaching:
    """Issue #34: Scoop normalised name set should be built once, not per call."""

    def test_normalised_set_built_once(self):
        normalize_calls = []
        original_normalize = __import__("wincoman.scoring", fromlist=["normalize_name"]).normalize_name

        def counting_normalize(name):
            normalize_calls.append(name)
            return original_normalize(name)

        from unittest.mock import patch

        mgr = ScoopManager(runner=_make_runner(SCOOP_LIST_OUTPUT))
        with patch("wincoman.matchers.scoop.normalize_name", side_effect=counting_normalize):
            mgr.is_managed("git")
            first_count = len(normalize_calls)
            mgr.is_managed("nodejs")
            second_count = len(normalize_calls)

        # Second call should add only 1 normalize call (for the display_name itself)
        # not rebuild the full set
        incremental = second_count - first_count
        assert incremental <= 1, f"Expected ≤1 normalize call, got {incremental}"
