"""Tests for src/wincoman/cache.py (Issue #26)."""
import json
import os

import pytest

from wincoman.cache import default_cache_path, load_cache, save_cache


class TestDefaultCachePath:
    def test_returns_string_under_home(self):
        path = default_cache_path()
        assert isinstance(path, str)
        assert os.path.expanduser("~") in path

    def test_contains_wincoman(self):
        assert "wincoman" in default_cache_path()


class TestSaveAndLoadCache:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "state.json")
        unmanaged = [{"name": "SomeApp", "version": "1.0"}]
        matches = [{"app_name": "SomeApp", "choco_id": "someapp"}]
        save_cache(path, unmanaged, matches)
        result = load_cache(path)
        assert result is not None
        loaded_unmanaged, loaded_matches = result
        assert loaded_unmanaged == unmanaged
        assert loaded_matches == matches

    def test_save_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "a" / "b" / "state.json")
        save_cache(path, [], [])
        assert os.path.exists(path)

    def test_save_writes_timestamp(self, tmp_path):
        path = str(tmp_path / "state.json")
        save_cache(path, [], [])
        with open(path) as fh:
            data = json.load(fh)
        assert "timestamp" in data


class TestLoadCache:
    def test_missing_file_returns_none(self, tmp_path):
        result = load_cache(str(tmp_path / "nonexistent.json"))
        assert result is None

    def test_corrupt_json_returns_none(self, tmp_path):
        path = str(tmp_path / "bad.json")
        with open(path, "w") as fh:
            fh.write("{not valid json}")
        result = load_cache(path)
        assert result is None

    def test_empty_json_object_returns_empty_lists(self, tmp_path):
        path = str(tmp_path / "empty.json")
        with open(path, "w") as fh:
            json.dump({}, fh)
        result = load_cache(path)
        assert result is not None
        unmanaged, matches = result
        assert unmanaged == []
        assert matches == []
