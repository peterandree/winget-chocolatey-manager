"""Tests for src/wincoman/cli.py (Issue #29)."""
import argparse

import pytest

from wincoman.cli import _build_arg_parser, _configure_logging
from wincoman.config import ScanConfig


class TestBuildArgParser:
    def _parse(self, *args):
        return _build_arg_parser().parse_args(list(args))

    def test_defaults(self):
        args = self._parse()
        assert args.dry_run is False
        assert args.auto is False
        assert args.export_only is False
        assert args.quiet is False
        assert args.use_cache is False

    def test_dry_run_flag(self):
        args = self._parse("--dry-run")
        assert args.dry_run is True

    def test_auto_flag(self):
        assert self._parse("--auto").auto is True

    def test_export_only_flag(self):
        assert self._parse("--export-only").export_only is True

    def test_quiet_flag(self):
        assert self._parse("--quiet").quiet is True
        assert self._parse("-q").quiet is True

    def test_exclude_microsoft_flag(self):
        assert self._parse("--exclude-microsoft").exclude_microsoft is True

    def test_min_score(self):
        assert self._parse("--min-score", "80").min_score == 80

    def test_use_cache_flag(self):
        assert self._parse("--use-cache").use_cache is True

    def test_output_flag(self):
        assert self._parse("--output", "/tmp/out.bat").output == "/tmp/out.bat"

    def test_cache_file_flag(self):
        assert self._parse("--cache-file", "/tmp/cache.json").cache_file == "/tmp/cache.json"

    def test_log_file_flag(self):
        assert self._parse("--log-file", "/tmp/app.log").log_file == "/tmp/app.log"

    def test_search_workers_flag(self):
        assert self._parse("--search-workers", "10").search_workers == 10

    def test_search_workers_default(self):
        assert self._parse().search_workers == 5

    def test_prog_name_is_wincoman(self):
        assert _build_arg_parser().prog == "wincoman"


class TestConfigureLogging:
    def test_quiet_sets_warning_level(self):
        import logging

        _configure_logging(ScanConfig(quiet=True))
        assert logging.getLogger().level == logging.WARNING

    def test_not_quiet_sets_info_level(self):
        import logging

        _configure_logging(ScanConfig(quiet=False))
        assert logging.getLogger().level == logging.INFO

    def test_log_file_adds_file_handler(self, tmp_path):
        import logging

        log_path = str(tmp_path / "app.log")
        _configure_logging(ScanConfig(log_file=log_path))
        handlers = logging.getLogger().handlers
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert any(log_path in h.baseFilename for h in file_handlers)
        # Clean up
        for h in file_handlers:
            h.close()

    def test_repeated_configure_does_not_stack_handlers(self):
        import logging

        _configure_logging(ScanConfig())
        count_before = len(logging.getLogger().handlers)
        _configure_logging(ScanConfig())
        count_after = len(logging.getLogger().handlers)
        assert count_after == count_before
