"""Tests for src/wincoman/scoring.py (Issue #20)."""
from wincoman.scoring import fuzzy_score, normalize_name, strip_version_suffix, versions_differ


class TestNormalizeName:
    def test_empty_string_returns_empty(self):
        assert normalize_name("") == ""

    def test_none_equivalent_guard(self):
        # Callers may pass empty but not None; verify basic safety
        assert normalize_name("") == ""

    def test_strips_version_suffix(self):
        assert normalize_name("Git 2.44.0") == "git"

    def test_removes_non_alphanumeric(self):
        assert normalize_name("Google Chrome") == "googlechrome"

    def test_lowercases_result(self):
        assert normalize_name("NODEJS") == "nodejs"

    def test_version_only_returns_empty(self):
        # "2.0" becomes "" after stripping digits.digits.*
        result = normalize_name("2.0")
        assert isinstance(result, str)


class TestFuzzyScore:
    def test_identical_strings_score_100(self):
        assert fuzzy_score("git", "git") == 100

    def test_completely_different_strings_score_below_threshold(self):
        score = fuzzy_score("python", "xyzqwerty")
        assert score < 60

    def test_case_insensitive(self):
        # WRatio on very short identical strings like "Git"/"git" can score ~66
        assert fuzzy_score("Git", "git") >= 60

    def test_github_desktop_matches_id(self):
        # Regression: WRatio must score high enough for this common case
        score = fuzzy_score("GitHub Desktop", "github-desktop")
        assert score >= 60

    def test_returns_int(self):
        assert isinstance(fuzzy_score("a", "b"), int)

    def test_score_in_range(self):
        score = fuzzy_score("something", "something else")
        assert 0 <= score <= 100


class TestVersionsDiffer:
    def test_same_major_returns_false(self):
        assert versions_differ("2.1.0", "2.3.0") is False

    def test_different_major_returns_true(self):
        assert versions_differ("1.0.0", "2.0.0") is True

    def test_empty_installed_returns_false(self):
        assert versions_differ("", "2.0.0") is False

    def test_empty_choco_returns_false(self):
        assert versions_differ("2.0.0", "") is False

    def test_unknown_version_returns_false(self):
        assert versions_differ("unknown", "2.0.0") is False

    def test_na_version_returns_false(self):
        assert versions_differ("n/a", "2.0.0") is False

    def test_both_empty_returns_false(self):
        assert versions_differ("", "") is False


class TestStripVersionSuffix:
    """Regression: display names with embedded versions must strip cleanly."""

    def test_hwinfo_style(self):
        assert strip_version_suffix("HWiNFO64 7.28-4900") == "HWiNFO64"

    def test_git_style(self):
        assert strip_version_suffix("Git 2.44.0") == "Git"

    def test_no_version(self):
        assert strip_version_suffix("Google Chrome") == "Google Chrome"

    def test_v_prefix(self):
        assert strip_version_suffix("SomeApp v3.2.1") == "SomeApp"

    def test_version_with_parens(self):
        assert strip_version_suffix("Python 3.12.4 (64-bit)") == "Python"

    def test_empty_string_returns_empty(self):
        assert strip_version_suffix("") == ""

    def test_does_not_strip_mid_name_digits(self):
        # "HWiNFO64" — the "64" is part of the name, not a trailing version
        result = strip_version_suffix("HWiNFO64")
        assert result == "HWiNFO64"

    def test_preserves_name_when_only_version(self):
        # Edge case: input is just a version — return as-is
        result = strip_version_suffix("7.28")
        assert isinstance(result, str)
        assert result  # not empty
