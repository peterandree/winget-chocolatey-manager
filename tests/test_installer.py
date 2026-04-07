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

    def test_multiple_packages_sleep_between(self):
        sleep_calls = []

        def runner(cmd, **kwargs):
            return "", "", 0

        import unittest.mock as _mock
        with _mock.patch("wincoman.installer.time") as mock_time:
            register_packages([_match("Git", "git"), _match("Node", "nodejs")], runner=runner)
        # sleep(0.5) should be called once (between the two installs)
        mock_time.sleep.assert_called_once_with(0.5)

    def test_failed_package_logged(self, caplog):
        def runner(cmd, **kwargs):
            return "", "some error", 1

        with caplog.at_level(logging.ERROR):
            register_packages([_match()], runner=runner)
        assert "Registration failed" in caplog.text

    def test_empty_list_returns_true(self):
        result = register_packages([])
        assert result is True


class TestRegisterInteractive:
    def test_choice_4_exits_without_registering(self):
        from wincoman.installer import register_interactive

        result = register_interactive([_match()], input_fn=lambda _: "4")
        assert result is True

    def test_choice_1_registers_all(self):
        from wincoman.installer import register_interactive

        installed = []

        def runner(cmd, **kwargs):
            installed.append(cmd)
            return "", "", 0

        result = register_interactive(
            [_match("Git", "git")],
            input_fn=lambda _: "1",
            runner=runner,
        )
        assert result is True
        assert any("git" in c for c in installed)

    def test_choice_2_select_yes(self):
        from wincoman.installer import register_interactive

        responses = iter(["2", "y"])

        def runner(cmd, **kwargs):
            return "", "", 0

        result = register_interactive(
            [_match()],
            input_fn=lambda _: next(responses),
            runner=runner,
        )
        assert result is True

    def test_choice_2_select_none_exits(self):
        from wincoman.installer import register_interactive

        responses = iter(["2", "n"])
        result = register_interactive(
            [_match()],
            input_fn=lambda _: next(responses),
        )
        assert result is True
