"""Tests for src/wincoman/config.py (Issue #21)."""
import argparse
import os

from wincoman.config import ScanConfig, _default_cache_path


class TestDefaultCachePath:
    def test_returns_string_under_home(self):
        path = _default_cache_path()
        assert isinstance(path, str)
        assert os.path.expanduser("~") in path

    def test_contains_wincoman(self):
        assert "wincoman" in _default_cache_path()


class TestScanConfigDefaults:
    def test_exclude_microsoft_default_false(self):
        assert ScanConfig().exclude_microsoft is False

    def test_min_score_default_60(self):
        assert ScanConfig().min_score == 60

    def test_dry_run_default_false(self):
        assert ScanConfig().dry_run is False

    def test_auto_default_false(self):
        assert ScanConfig().auto is False

    def test_export_only_default_false(self):
        assert ScanConfig().export_only is False

    def test_use_cache_default_false(self):
        assert ScanConfig().use_cache is False

    def test_command_timeout_default_60(self):
        assert ScanConfig().command_timeout == 60

    def test_search_delay_default_0_1(self):
        assert ScanConfig().search_delay == 0.1

    def test_quiet_default_false(self):
        assert ScanConfig().quiet is False

    def test_log_file_default_none(self):
        assert ScanConfig().log_file is None

    def test_cache_path_is_string(self):
        assert isinstance(ScanConfig().cache_path, str)


class TestScanConfigFromNamespace:
    def _ns(self, **kwargs):
        defaults = dict(
            exclude_microsoft=False,
            min_score=0,
            dry_run=False,
            auto=False,
            export_only=False,
            output=None,
            use_cache=False,
            cache_file=None,
            quiet=False,
            log_file=None,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_dry_run_true_propagates(self):
        cfg = ScanConfig.from_namespace(self._ns(dry_run=True))
        assert cfg.dry_run is True

    def test_min_score_zero_uses_default(self):
        cfg = ScanConfig.from_namespace(self._ns(min_score=0))
        # 0 means "not set" — from_namespace maps it to 0 (caller applies class default)
        assert cfg.min_score == 0

    def test_min_score_custom_value(self):
        cfg = ScanConfig.from_namespace(self._ns(min_score=80))
        assert cfg.min_score == 80

    def test_cache_file_none_uses_default_path(self):
        cfg = ScanConfig.from_namespace(self._ns(cache_file=None))
        assert "wincoman" in cfg.cache_path

    def test_cache_file_custom_path(self):
        cfg = ScanConfig.from_namespace(self._ns(cache_file="/tmp/cache.json"))
        assert cfg.cache_path == "/tmp/cache.json"

    def test_exclude_microsoft_propagates(self):
        cfg = ScanConfig.from_namespace(self._ns(exclude_microsoft=True))
        assert cfg.exclude_microsoft is True

    def test_output_path_propagates(self):
        cfg = ScanConfig.from_namespace(self._ns(output="/tmp/out.bat"))
        assert cfg.output_path == "/tmp/out.bat"
