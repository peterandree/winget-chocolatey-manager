"""Tests for src/wincoman/cache.py (Issues #26, #39)."""
import json
import os

import pytest

from wincoman.cache import default_cache_path, load_cache, save_cache
from wincoman.matchers.base import AppCandidates, PackageMatch


def _candidate(app="SomeApp"):
    pm = PackageMatch(app, "1.0", "someapp", "1.0.0", False, "chocolatey")
    return AppCandidates(app, "1.0", primary=pm)


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
        candidates = [_candidate()]
        save_cache(path, unmanaged, candidates)
        result = load_cache(path)
        assert result is not None
        loaded_unmanaged, loaded_candidates = result
        assert loaded_unmanaged == unmanaged
        assert len(loaded_candidates) == 1
        assert loaded_candidates[0].app_name == "SomeApp"
        assert loaded_candidates[0].primary.pkg_id == "someapp"

    def test_round_trip_with_alternatives(self, tmp_path):
        path = str(tmp_path / "state.json")
        pm1 = PackageMatch("Git", "2.44", "Git.Git", "2.44.0", False, "winget")
        pm2 = PackageMatch("Git", "2.44", "git", "2.44.0", False, "chocolatey")
        cand = AppCandidates("Git", "2.44", primary=pm1, alternatives=[pm2])
        save_cache(path, [], [cand])
        result = load_cache(path)
        assert result is not None
        _, loaded = result
        assert loaded[0].primary.manager == "winget"
        assert len(loaded[0].alternatives) == 1
        assert loaded[0].alternatives[0].manager == "chocolatey"

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

    def test_save_writes_schema_version_2(self, tmp_path):
        path = str(tmp_path / "state.json")
        save_cache(path, [], [])
        with open(path) as fh:
            data = json.load(fh)
        assert data.get("schema_version") == 2


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

    def test_empty_json_object_returns_none(self, tmp_path):
        """An empty JSON object has no recognized keys — returns None."""
        path = str(tmp_path / "empty.json")
        with open(path, "w") as fh:
            json.dump({}, fh)
        result = load_cache(path)
        assert result is None

    def test_v1_compat_loads_matches_key(self, tmp_path):
        """Schema v1 cache (``matches`` key) is wrapped in AppCandidates."""
        path = str(tmp_path / "v1.json")
        v1_data = {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "unmanaged_apps": [{"name": "Git"}],
            "matches": [
                {"app_name": "Git", "app_version": "2.44", "pkg_id": "git",
                 "pkg_version": "2.44.0", "version_mismatch": False, "manager": "chocolatey"}
            ],
        }
        with open(path, "w") as fh:
            json.dump(v1_data, fh)
        result = load_cache(path)
        assert result is not None
        unmanaged, candidates = result
        assert len(candidates) == 1
        assert isinstance(candidates[0], AppCandidates)
        assert candidates[0].primary.pkg_id == "git"
