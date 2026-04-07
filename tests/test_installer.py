"""Tests for src/wincoman/installer.py (Issue #28)."""
import logging

from wincoman.config import ScanConfig
from wincoman.installer import register_packages
from wincoman.matchers.base import PackageMatch


def _match(app_name="Git", pkg_id="git"):
    return PackageMatch(
        app_name=app_name,
        app_version="2.44",
        pkg_id=pkg_id,
        pkg_version="2.44.0",
        version_mismatch=False,
        manager="chocolatey",
    )


class TestRegisterPackages:
    def test_dry_run_skips_install(self, caplog):
        config = ScanConfig(dry_run=True)
        with caplog.at_level(logging.INFO):
            result = register_packages([_match()], config)
        assert result is True
        assert "DRY-RUN" in caplog.text

    def test_dry_run_does_not_call_runner(self):
        runner_calls = []

        def runner(cmd, **kwargs):
            runner_calls.append(cmd)
            return "", "", 0

        config = ScanConfig(dry_run=True)
        register_packages([_match()], config, runner=runner)
        assert runner_calls == []

    def test_successful_install_returns_true(self):
        def runner(cmd, **kwargs):
            return "Installed successfully", "", 0

        config = ScanConfig(dry_run=False)
        result = register_packages([_match()], config, runner=runner)
        assert result is True

    def test_failed_install_returns_false(self):
        def runner(cmd, **kwargs):
            return "", "Error: package not found", 1

        config = ScanConfig(dry_run=False)
        result = register_packages([_match()], config, runner=runner)
        assert result is False

    def test_uses_choco_install_command(self):
        captured = []

        def runner(cmd, **kwargs):
            captured.append(cmd)
            return "", "", 0

        register_packages([_match("Git", "git")], runner=runner)
        assert any("choco" in c and "install" in c and "git" in c for c in captured)

    def test_no_skip_ps_scripts(self):
        """Regression: -n (skip PS) must not appear in install command."""
        captured = []

        def runner(cmd, **kwargs):
            captured.append(cmd)
            return "", "", 0

        register_packages([_match()], runner=runner)
        for cmd in captured:
            assert "-n" not in cmd

    def test_accepts_legacy_dicts(self):
        def runner(cmd, **kwargs):
            return "", "", 0

        legacy = [{"app_name": "OldApp", "choco_id": "oldapp"}]
        result = register_packages(legacy, runner=runner)
        assert result is True

    def test_empty_list_returns_true(self):
        result = register_packages([])
        assert result is True
