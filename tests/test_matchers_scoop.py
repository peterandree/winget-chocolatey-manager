"""Tests for src/wincoman/matchers/scoop.py (Issue #23)."""
from wincoman.matchers.scoop import ScoopManager


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
