"""Tests for src/wincoman/reporter.py (Issues #28, #37)."""
import logging
import os

import pytest

from wincoman.matchers.base import PackageMatch
from wincoman.reporter import ScanSummary, display_results, display_summary, export_to_batch


def _match(app_name="Git", pkg_id="git", mismatch=False):
    return PackageMatch(
        app_name=app_name,
        app_version="2.44",
        pkg_id=pkg_id,
        pkg_version="2.44.0",
        version_mismatch=mismatch,
        manager="chocolatey",
    )


class TestDisplayResults:
    def test_logs_match_names(self, caplog):
        with caplog.at_level(logging.INFO):
            display_results([_match("Git", "git")])
        assert "Git" in caplog.text
        assert "git" in caplog.text

    def test_short_name_not_truncated(self, caplog):
        with caplog.at_level(logging.INFO):
            display_results([_match("ShortApp")])
        assert "..." not in caplog.text

    def test_long_name_truncated(self, caplog):
        with caplog.at_level(logging.INFO):
            display_results([_match("A" * 80)])
        assert "..." in caplog.text

    def test_version_mismatch_flag_shown(self, caplog):
        with caplog.at_level(logging.INFO):
            display_results([_match(mismatch=True)])
        assert "mismatch" in caplog.text.lower()

    def test_accepts_legacy_dicts(self, caplog):
        legacy = [{"app_name": "OldApp", "choco_id": "oldapp", "version_mismatch": False}]
        with caplog.at_level(logging.INFO):
            display_results(legacy)
        assert "OldApp" in caplog.text


class TestExportToBatch:
    def test_creates_timestamped_file_by_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        export_to_batch([_match()])
        bat_files = list(tmp_path.glob("register_unmanaged_apps_*.bat"))
        assert len(bat_files) == 1

    def test_explicit_path_used(self, tmp_path):
        out = tmp_path / "out.bat"
        result = export_to_batch([_match()], str(out))
        assert result is True
        assert out.exists()

    def test_batch_contains_choco_install(self, tmp_path):
        out = tmp_path / "out.bat"
        export_to_batch([_match("Git", "git")], str(out))
        content = out.read_text()
        assert "choco install git" in content

    def test_prompts_before_overwrite(self, tmp_path):
        out = tmp_path / "out.bat"
        out.write_text("old content")
        result = export_to_batch([_match()], str(out), input_fn=lambda _: "y")
        assert result is True
        assert "choco install" in out.read_text()

    def test_cancels_on_no(self, tmp_path):
        out = tmp_path / "out.bat"
        out.write_text("old content")
        result = export_to_batch([_match()], str(out), input_fn=lambda _: "n")
        assert result is False
        assert out.read_text() == "old content"

    def test_returns_false_on_write_error(self, tmp_path):
        # A directory path causes an IsADirectoryError / PermissionError on write
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        # Pass input_fn=lambda _: "y" so the overwrite prompt doesn't block
        result = export_to_batch([_match()], str(subdir), input_fn=lambda _: "y")
        assert result is False


class TestScanSummary:
    """Issue #37: ScanSummary accumulates stats from callbacks."""

    def test_record_classification_managed(self):
        s = ScanSummary()
        s.record_classification("Git", "winget")
        s.record_classification("VLC", "chocolatey")
        assert s.total_scanned == 2
        assert s.managed_by == {"winget": 1, "chocolatey": 1}
        assert s.local_only == 0

    def test_record_classification_unmanaged(self):
        s = ScanSummary()
        s.record_classification("FooApp", None)
        assert s.total_scanned == 1
        assert s.local_only == 1
        assert s.managed_by == {}

    def test_record_search_result_found(self):
        s = ScanSummary()
        s.record_search_result("Git", _match())
        assert s.choco_matches_found == 1
        assert s.choco_no_match == 0

    def test_record_search_result_not_found(self):
        s = ScanSummary()
        s.record_search_result("FooApp", None)
        assert s.choco_matches_found == 0
        assert s.choco_no_match == 1

    def test_combined_stats(self):
        s = ScanSummary()
        s.record_classification("Git", "winget")
        s.record_classification("VLC", "winget")
        s.record_classification("FooApp", None)
        s.record_classification("BarApp", None)
        s.record_search_result("FooApp", _match("FooApp", "fooapp"))
        s.record_search_result("BarApp", None)
        assert s.total_scanned == 4
        assert s.managed_by == {"winget": 2}
        assert s.local_only == 2
        assert s.choco_matches_found == 1
        assert s.choco_no_match == 1


class TestDisplaySummary:
    """Issue #37: display_summary logs a formatted block."""

    def test_shows_total_and_managers(self, caplog):
        s = ScanSummary()
        s.record_classification("Git", "winget")
        s.record_classification("VLC", "chocolatey")
        s.record_classification("Foo", None)
        with caplog.at_level(logging.INFO):
            display_summary(s)
        assert "SCAN SUMMARY" in caplog.text
        assert "3" in caplog.text  # total
        assert "winget" in caplog.text
        assert "chocolatey" in caplog.text
        assert "Local only" in caplog.text

    def test_shows_choco_search_stats(self, caplog):
        s = ScanSummary()
        s.record_search_result("Git", _match())
        s.record_search_result("Foo", None)
        with caplog.at_level(logging.INFO):
            display_summary(s)
        assert "Package manager matches found" in caplog.text
        assert "No package manager match" in caplog.text

    def test_omits_choco_section_when_no_search_done(self, caplog):
        s = ScanSummary()
        s.record_classification("Git", "winget")
        with caplog.at_level(logging.INFO):
            display_summary(s)
        assert "Package manager matches" not in caplog.text

    def test_empty_summary_still_renders(self, caplog):
        s = ScanSummary()
        with caplog.at_level(logging.INFO):
            display_summary(s)
        assert "SCAN SUMMARY" in caplog.text
        assert "0" in caplog.text
