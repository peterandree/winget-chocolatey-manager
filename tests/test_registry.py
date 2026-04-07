"""Tests for src/wincoman/registry.py (Issue #25)."""
import json
from unittest.mock import patch

from wincoman.config import ScanConfig
from wincoman.registry import _deduplicate, scan_installed_programs


# ---------------------------------------------------------------------------
# _deduplicate (pure function — no subprocess needed)
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def test_no_duplicates_unchanged(self):
        programs = [
            {"DisplayName": "App A", "DisplayVersion": "1.0", "Publisher": "X"},
            {"DisplayName": "App B", "DisplayVersion": "2.0", "Publisher": "Y"},
        ]
        assert len(_deduplicate(programs)) == 2

    def test_exact_duplicate_removed(self):
        programs = [
            {"DisplayName": "Git", "DisplayVersion": "2.44"},
            {"DisplayName": "Git", "DisplayVersion": "2.44"},
        ]
        assert len(_deduplicate(programs)) == 1

    def test_first_occurrence_kept(self):
        programs = [
            {"DisplayName": "MyApp", "DisplayVersion": "64bit-version"},
            {"DisplayName": "MyApp", "DisplayVersion": "32bit-version"},
        ]
        result = _deduplicate(programs)
        assert len(result) == 1
        assert result[0]["DisplayVersion"] == "64bit-version"

    def test_case_insensitive_dedup(self):
        programs = [
            {"DisplayName": "MyApp", "DisplayVersion": "1.0"},
            {"DisplayName": "myapp", "DisplayVersion": "1.0"},
            {"DisplayName": "MYAPP", "DisplayVersion": "1.0"},
        ]
        assert len(_deduplicate(programs)) == 1

    def test_empty_display_name_excluded(self):
        programs = [
            {"DisplayName": "", "DisplayVersion": "1.0"},
            {"DisplayName": "RealApp", "DisplayVersion": "2.0"},
        ]
        result = _deduplicate(programs)
        assert len(result) == 1

    def test_none_display_name_excluded(self):
        programs = [
            {"DisplayName": None, "DisplayVersion": "1.0"},
            {"DisplayName": "RealApp", "DisplayVersion": "2.0"},
        ]
        result = _deduplicate(programs)
        assert len(result) == 1

    def test_empty_list_returns_empty(self):
        assert _deduplicate([]) == []


# ---------------------------------------------------------------------------
# scan_installed_programs
# ---------------------------------------------------------------------------


class TestScanInstalledPrograms:
    def _runner_with_json(self, programs):
        data = json.dumps(programs)

        def runner(cmd, **kwargs):
            return data, "", 0

        return runner

    def test_returns_list_of_dicts(self):
        programs = [{"DisplayName": "Git", "DisplayVersion": "2.44", "Publisher": "X"}]
        result = scan_installed_programs(runner=self._runner_with_json(programs))
        assert isinstance(result, list)
        assert result[0]["DisplayName"] == "Git"

    def test_deduplicates_results(self):
        programs = [
            {"DisplayName": "Git", "DisplayVersion": "2.44"},
            {"DisplayName": "Git", "DisplayVersion": "2.44"},
        ]
        result = scan_installed_programs(runner=self._runner_with_json(programs))
        assert len(result) == 1

    def test_returns_empty_on_runner_failure(self):
        def runner(cmd, **kwargs):
            return "", "error", 1

        result = scan_installed_programs(runner=runner)
        assert result == []

    def test_returns_empty_on_empty_stdout(self):
        def runner(cmd, **kwargs):
            return "", "", 0

        result = scan_installed_programs(runner=runner)
        assert result == []

    def test_returns_empty_on_invalid_json(self):
        def runner(cmd, **kwargs):
            return "not json", "", 0

        result = scan_installed_programs(runner=runner)
        assert result == []

    def test_single_dict_wrapped_in_list(self):
        """PowerShell returns a plain object (not array) when there's one result."""
        single = {"DisplayName": "OnlyApp", "DisplayVersion": "1.0", "Publisher": "X"}

        def runner(cmd, **kwargs):
            return json.dumps(single), "", 0

        result = scan_installed_programs(runner=runner)
        assert len(result) == 1

    def test_exclude_microsoft_filter_in_script(self):
        """Verify the exclude_microsoft flag changes the PowerShell script."""
        captured_scripts = []

        def runner(cmd, **kwargs):
            # cmd is ["powershell", "-Command", <script>]
            captured_scripts.append(cmd[2])
            return json.dumps([]), "", 0

        config = ScanConfig(exclude_microsoft=True)
        scan_installed_programs(config, runner=runner)
        assert "notmatch" in captured_scripts[0].lower() or "notmatch" in captured_scripts[0]

    def test_no_microsoft_filter_by_default(self):
        captured_scripts = []

        def runner(cmd, **kwargs):
            captured_scripts.append(cmd[2])
            return json.dumps([]), "", 0

        scan_installed_programs(runner=runner)
        assert "notmatch" not in captured_scripts[0]
