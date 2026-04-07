"""Tests for src/wincoman/installer.py (Issues #28, #40)."""
import logging
from unittest.mock import MagicMock

from wincoman.config import ScanConfig
from wincoman.installer import register_packages
from wincoman.matchers.base import AppCandidates, PackageMatch


def _match(app_name="Git", pkg_id="git", manager="chocolatey"):
    return PackageMatch(
        app_name=app_name,
        app_version="2.44",
        pkg_id=pkg_id,
        pkg_version="2.44.0",
        version_mismatch=False,
        manager=manager,
    )


def _candidate(app_name="Git", pkg_id="git", manager="winget", alt_manager=None):
    primary = _match(app_name, pkg_id, manager)
    alts = [_match(app_name, f"{pkg_id}-alt", alt_manager)] if alt_manager else []
    return AppCandidates(app_name, "2.44", primary=primary, alternatives=alts)


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


class TestRegisterPackagesManagerDispatch:
    """Issue #40: register_packages routes install to the correct manager adapter."""

    def test_routes_to_winget_manager(self):
        """When managers dict is provided, winget match calls winget.install()."""
        winget_mgr = MagicMock()
        winget_mgr.install.return_value = True
        managers = {"winget": winget_mgr}

        result = register_packages(
            [_candidate("Git", "Git.Git", "winget")],
            managers=managers,
        )
        assert result is True
        winget_mgr.install.assert_called_once()
        call_args = winget_mgr.install.call_args
        assert call_args[0][0].pkg_id == "Git.Git"

    def test_routes_to_choco_manager(self):
        """Chocolatey match calls choco.install()."""
        choco_mgr = MagicMock()
        choco_mgr.install.return_value = True
        managers = {"chocolatey": choco_mgr}

        result = register_packages(
            [_candidate("Git", "git", "chocolatey")],
            managers=managers,
        )
        assert result is True
        choco_mgr.install.assert_called_once()

    def test_install_failure_via_manager_returns_false(self):
        winget_mgr = MagicMock()
        winget_mgr.install.return_value = False
        managers = {"winget": winget_mgr}

        result = register_packages(
            [_candidate("Git", "Git.Git", "winget")],
            managers=managers,
        )
        assert result is False

    def test_dry_run_does_not_call_manager_install(self):
        winget_mgr = MagicMock()
        managers = {"winget": winget_mgr}
        config = ScanConfig(dry_run=True)

        result = register_packages(
            [_candidate("Git", "Git.Git", "winget")],
            config,
            managers=managers,
        )
        assert result is True
        winget_mgr.install.assert_not_called()

    def test_accepts_app_candidates(self):
        """AppCandidates entries are resolved to primary match."""
        choco_mgr = MagicMock()
        choco_mgr.install.return_value = True
        managers = {"chocolatey": choco_mgr}

        cand = _candidate("VLC", "vlc", "chocolatey")
        result = register_packages([cand], managers=managers)
        assert result is True
        assert choco_mgr.install.call_args[0][0].app_name == "VLC"


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


class TestRegisterInteractiveManagerSelection:
    """Issue #41: Choice 2 shows manager alternatives for AppCandidates."""

    def _candidate_with_alts(self, app="Git"):
        pm_wg = PackageMatch(app, "2.44", f"{app}.{app}", "2.44.0", False, "winget")
        pm_ch = PackageMatch(app, "2.44", app.lower(), "2.44.0", False, "chocolatey")
        return AppCandidates(app, "2.44", primary=pm_wg, alternatives=[pm_ch])

    def test_choice_2_single_manager_yes(self):
        from wincoman.installer import register_interactive

        runner_calls = []

        def runner(cmd, **kw):
            runner_calls.append(cmd)
            return "", "", 0

        cand = AppCandidates(
            "Git", "2.44",
            primary=PackageMatch("Git", "2.44", "git", "2.44.0", False, "chocolatey"),
        )
        responses = iter(["2", "y"])
        result = register_interactive(
            [cand],
            input_fn=lambda _: next(responses),
            runner=runner,
        )
        assert result is True

    def test_choice_2_multi_manager_picks_alternative(self):
        """User selects option 2 (chocolatey) instead of option 1 (winget)."""
        from wincoman.installer import register_interactive

        choco_mgr = MagicMock()
        choco_mgr.install.return_value = True
        managers = {"chocolatey": choco_mgr, "winget": MagicMock()}

        cand = self._candidate_with_alts("Git")
        # "2" = select option 2 (chocolatey alternative)
        responses = iter(["2", "2"])
        result = register_interactive(
            [cand],
            input_fn=lambda _: next(responses),
            managers=managers,
        )
        assert result is True
        choco_mgr.install.assert_called_once()
        installed_match = choco_mgr.install.call_args[0][0]
        assert installed_match.manager == "chocolatey"

    def test_choice_2_multi_manager_skip(self):
        """User skips by choosing the 'skip' option."""
        from wincoman.installer import register_interactive

        cand = self._candidate_with_alts("Git")
        # "2" = review, "3" = skip (since there are 2 managers, skip = option 3)
        responses = iter(["2", "3"])
        result = register_interactive(
            [cand],
            input_fn=lambda _: next(responses),
        )
        assert result is True

    def test_choice_2_multi_manager_picks_primary(self):
        """User selects option 1 (winget primary)."""
        from wincoman.installer import register_interactive

        winget_mgr = MagicMock()
        winget_mgr.install.return_value = True
        managers = {"winget": winget_mgr, "chocolatey": MagicMock()}

        cand = self._candidate_with_alts("Git")
        # "2" = review mode, "1" = pick winget (primary)
        responses = iter(["2", "1"])
        result = register_interactive(
            [cand],
            input_fn=lambda _: next(responses),
            managers=managers,
        )
        assert result is True
        winget_mgr.install.assert_called_once()
        installed_match = winget_mgr.install.call_args[0][0]
        assert installed_match.manager == "winget"
