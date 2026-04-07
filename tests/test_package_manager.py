"""Tests for register_unmanaged_apps.py (backward-compat shim)"""
import sys
import os
import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock, call
from io import StringIO

from register_unmanaged_apps import PackageManager


# ---------------------------------------------------------------------------
# Issue #17 — display_results() truncation off-by-one
# ---------------------------------------------------------------------------

class TestDisplayResults:
    def _manager_with_matches(self, matches):
        pm = PackageManager()
        pm.matches = matches
        return pm

    def test_short_name_not_truncated(self, caplog):
        import logging as _logging
        pm = self._manager_with_matches([{'app_name': 'ShortApp', 'choco_id': 'shortapp'}])
        with caplog.at_level(_logging.INFO):
            pm.display_results()
        assert 'ShortApp' in caplog.text
        assert '...' not in caplog.text

    def test_exactly_39_chars_not_truncated(self, caplog):
        import logging as _logging
        name = 'A' * 39
        pm = self._manager_with_matches([{'app_name': name, 'choco_id': 'pkg'}])
        with caplog.at_level(_logging.INFO):
            pm.display_results()
        assert '...' not in caplog.text

    def test_name_40_chars_is_truncated(self, caplog):
        import logging as _logging
        name = 'A' * 40
        pm = self._manager_with_matches([{'app_name': name, 'choco_id': 'pkg'}])
        with caplog.at_level(_logging.INFO):
            pm.display_results()
        assert '...' in caplog.text

    def test_truncated_display_fits_in_40_chars(self, caplog):
        import logging as _logging
        name = 'A' * 80
        pm = self._manager_with_matches([{'app_name': name, 'choco_id': 'pkg'}])
        with caplog.at_level(_logging.INFO):
            pm.display_results()
        # caplog.records gives us the raw message without log-level prefixes
        messages = [r.getMessage() for r in caplog.records]
        table_line = next((m for m in messages if '...' in m and 'pkg' in m), None)
        assert table_line is not None, 'No truncated table line found in log output'
        # The table format is "{app_display:<40} {choco_id:<30}"
        app_display = table_line[:40].rstrip()
        assert len(app_display) <= 39, f"Truncated name overflows column: '{app_display}'"


# ---------------------------------------------------------------------------
# Issue #15 — Registry scan deduplication
# ---------------------------------------------------------------------------

class TestGetInstalledProgramsDedup:
    def _run_with_json(self, programs_json: str):
        pm = PackageManager()
        with patch.object(PackageManager, 'run_command', return_value=(programs_json, '', 0)):
            pm.get_installed_programs()
        return pm.installed_programs

    def test_no_duplicates_when_unique(self):
        data = json.dumps([
            {'DisplayName': 'App A', 'DisplayVersion': '1.0', 'Publisher': 'X'},
            {'DisplayName': 'App B', 'DisplayVersion': '2.0', 'Publisher': 'Y'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 2

    def test_duplicates_removed(self):
        data = json.dumps([
            {'DisplayName': 'Git', 'DisplayVersion': '2.44', 'Publisher': 'GitForWindows'},
            {'DisplayName': 'Git', 'DisplayVersion': '2.44', 'Publisher': 'GitForWindows'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 1

    def test_first_occurrence_preferred(self):
        """HKLM 64-bit (first in list) should be kept over WOW6432Node duplicate."""
        data = json.dumps([
            {'DisplayName': 'MyApp', 'DisplayVersion': '64bit-version', 'Publisher': 'Pub'},
            {'DisplayName': 'MyApp', 'DisplayVersion': '32bit-version', 'Publisher': 'Pub'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 1
        assert result[0]['DisplayVersion'] == '64bit-version'

    def test_case_insensitive_dedup(self):
        data = json.dumps([
            {'DisplayName': 'MyApp', 'DisplayVersion': '1.0', 'Publisher': 'X'},
            {'DisplayName': 'myapp', 'DisplayVersion': '1.0', 'Publisher': 'X'},
            {'DisplayName': 'MYAPP', 'DisplayVersion': '1.0', 'Publisher': 'X'},
        ])
        result = self._run_with_json(data)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Issue #14 — run_command timeout
# ---------------------------------------------------------------------------

class TestRunCommandTimeout:
    def test_timeout_returns_error_tuple(self):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=['choco'], timeout=60)):
            stdout, stderr, code = PackageManager.run_command(['choco', 'search', 'something'])
        assert stdout == ''
        assert 'timed out' in stderr.lower()
        assert code == 1

    def test_timeout_passed_to_subprocess(self):
        with patch('subprocess.run', return_value=MagicMock(stdout='ok', stderr='', returncode=0)) as mock_run:
            PackageManager.run_command(['choco', '--version'])
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert 'timeout' in kwargs
        assert kwargs['timeout'] == PackageManager.COMMAND_TIMEOUT

    def test_custom_timeout_respected(self):
        with patch('subprocess.run', return_value=MagicMock(stdout='ok', stderr='', returncode=0)) as mock_run:
            PackageManager.run_command(['choco', '--version'], timeout=5)
        _, kwargs = mock_run.call_args
        assert kwargs['timeout'] == 5


# ---------------------------------------------------------------------------
# Issue #12 — choco list --limit-output deprecated in v2
# ---------------------------------------------------------------------------

class TestChocoVersionCompat:
    def _get_packages_with_version(self, version_str: str):
        pm = PackageManager()
        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return 'git|2.44.0\n', '', 0

        with patch.object(PackageManager, 'get_choco_major_version', return_value=int(version_str.split('.')[0])):
            with patch.object(PackageManager, 'run_command', side_effect=fake_run):
                pm.get_chocolatey_packages()
        return captured_cmds

    def test_v1_uses_limit_output(self):
        cmds = self._get_packages_with_version('1.4.0')
        assert any('--limit-output' in c for c in cmds)

    def test_v2_omits_limit_output(self):
        cmds = self._get_packages_with_version('2.3.0')
        assert not any('--limit-output' in c for c in cmds)

    def test_get_choco_major_version_parses_version(self):
        with patch('subprocess.run', return_value=MagicMock(stdout='2.3.0\n', returncode=0)):
            assert PackageManager.get_choco_major_version() == 2

    def test_get_choco_major_version_returns_zero_on_error(self):
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            assert PackageManager.get_choco_major_version() == 0


# ---------------------------------------------------------------------------
# Issue #5 -- Admin check is non-blocking
# ---------------------------------------------------------------------------

class TestAdminCheck:
    def _run_prereq(self, is_admin: bool):
        pm = PackageManager()
        with patch.object(PackageManager, 'run_command', return_value=('v1.0\n', '', 0)):
            with patch('ctypes.windll.shell32.IsUserAnAdmin', return_value=int(is_admin)):
                return pm.check_prerequisites()

    def test_returns_false_when_not_admin(self):
        result = self._run_prereq(is_admin=False)
        assert result is False

    def test_returns_true_when_admin(self):
        result = self._run_prereq(is_admin=True)
        assert result is True


# ---------------------------------------------------------------------------
# Issue #6 -- PowerShell filter excludes Microsoft apps (now opt-in)
# ---------------------------------------------------------------------------

class TestMicrosoftFilter:
    def _get_ps_script(self, exclude_microsoft: bool) -> str:
        pm = PackageManager(exclude_microsoft=exclude_microsoft)
        captured = []
        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return '[]', '', 0
        with patch.object(PackageManager, 'run_command', side_effect=fake_run):
            pm.get_installed_programs()
        for cmd in captured:
            if 'powershell' in cmd[0].lower():
                return cmd[-1]
        return ''

    def test_microsoft_included_by_default(self):
        script = self._get_ps_script(exclude_microsoft=False)
        assert 'notmatch' not in script.lower()

    def test_microsoft_excluded_when_flag_set(self):
        script = self._get_ps_script(exclude_microsoft=True)
        assert 'notmatch' in script.lower()


# ---------------------------------------------------------------------------
# Issue #4 -- choco install -n skips PowerShell scripts
# ---------------------------------------------------------------------------

class TestChocoInstallNoSkipPS:
    def test_install_cmd_has_no_n_flag(self):
        pm = PackageManager()
        pm.matches = [{'app_name': 'Git', 'choco_id': 'git', 'app_version': '2.44', 'choco_version': '2.44'}]
        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return '', '', 0

        with patch.object(PackageManager, 'run_command', side_effect=fake_run):
            with patch('builtins.input', return_value='1'):
                pm.register_packages_interactive()

        install_cmds = [c for c in captured_cmds if 'install' in c]
        assert install_cmds, 'Expected at least one install command'
        for cmd in install_cmds:
            assert '-n' not in cmd, f'-n flag found in install command: {cmd}'
            assert '--skippowershell' not in cmd

    def test_export_batch_has_no_n_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pm = PackageManager()
        pm.matches = [{'app_name': 'Git', 'choco_id': 'git', 'app_version': '2.44', 'choco_version': '2.44'}]
        out_path = tmp_path / 'out.bat'
        pm.export_to_batch(output_path=str(out_path))
        content = out_path.read_text()
        assert '-n' not in content


# ---------------------------------------------------------------------------
# Issue #1 -- WinGet JSON parser
# ---------------------------------------------------------------------------

class TestGetWingetPackages:
    def test_parses_json_output(self):
        packages = [
            {'Name': 'GitHub Desktop', 'Id': 'GitHub.GitHubDesktop', 'Version': '3.3'},
            {'Name': '7-Zip 24.01 (x64)', 'Id': '7zip.7zip', 'Version': '24.01'},
        ]
        pm = PackageManager()
        with patch.object(PackageManager, 'run_command', return_value=(json.dumps(packages), '', 0)):
            pm.get_winget_packages()
        assert 'github desktop' in pm.winget_apps
        assert '7-zip 24.01 (x64)' in pm.winget_apps

    def test_names_with_spaces_preserved(self):
        packages = [{'Name': 'Visual Studio Code', 'Id': 'Microsoft.VisualStudioCode', 'Version': '1.89'}]
        pm = PackageManager()
        with patch.object(PackageManager, 'run_command', return_value=(json.dumps(packages), '', 0)):
            pm.get_winget_packages()
        assert 'visual studio code' in pm.winget_apps

    def test_invalid_json_returns_false(self):
        pm = PackageManager()
        with patch.object(PackageManager, 'run_command', return_value=('not json', '', 0)):
            result = pm.get_winget_packages()
        assert result is False


# ---------------------------------------------------------------------------
# Issue #2 -- fuzzy_score replaces lossy normalize_name matching
# ---------------------------------------------------------------------------

class TestFuzzyScore:
    def test_exact_match_is_100(self):
        assert PackageManager.fuzzy_score('Git', 'Git') == 100

    def test_github_desktop_matches_github_desktop_pkg(self):
        # WRatio handles case and punctuation differences
        score = PackageManager.fuzzy_score('GitHub Desktop', 'github-desktop')
        assert score >= 60, f'Expected >= 60, got {score}'

    def test_seven_zip_matches(self):
        score = PackageManager.fuzzy_score('7-Zip', '7zip')
        assert score >= 60, f'Expected >= 60, got {score}'

    def test_unrelated_strings_score_low(self):
        score = PackageManager.fuzzy_score('Python 3.12', 'node')
        assert score < 50


# ---------------------------------------------------------------------------
# Issue #3 -- approximate search scores candidates, picks best above threshold
# ---------------------------------------------------------------------------

class TestApproxSearchScoring:
    def _run_search(self, app_name: str, choco_output: str):
        pm = PackageManager()
        pm.unmanaged_apps = [{'name': app_name, 'version': '1.0'}]
        call_count = {'n': 0}

        def fake_run(cmd, **kwargs):
            call_count['n'] += 1
            if '--exact' in cmd:
                return '', '', 1  # exact search fails
            return choco_output, '', 0

        with patch.object(PackageManager, 'run_command', side_effect=fake_run):
            with patch.object(PackageManager, 'get_choco_major_version', return_value=1):
                with patch('time.sleep'):
                    pm.search_chocolatey_matches()
        return pm.matches

    def test_best_scoring_candidate_selected(self):
        choco_out = '7zip.commandline|24.01\n7zip|24.01\n7zip.install|24.01\n'
        matches = self._run_search('7-Zip', choco_out)
        # 7zip should score higher than 7zip.commandline for '7-Zip'
        if matches:
            assert matches[0]['choco_id'] in ('7zip', '7zip.install')

    def test_low_score_candidate_rejected(self):
        # 'completelydifferentapp' should score very low against '7-Zip'
        choco_out = 'completelydifferentapp|1.0\n'
        matches = self._run_search('7-Zip', choco_out)
        assert matches == []


# ---------------------------------------------------------------------------
# Issue #16 -- export_to_batch silently overwrites previous export
# ---------------------------------------------------------------------------

class TestExportToBatch:
    def _pm_with_matches(self):
        pm = PackageManager()
        pm.matches = [{'app_name': 'Git', 'choco_id': 'git'}]
        return pm

    def test_creates_timestamped_file_by_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pm = self._pm_with_matches()
        pm.export_to_batch()
        bat_files = list(tmp_path.glob('register_unmanaged_apps_*.bat'))
        assert len(bat_files) == 1

    def test_explicit_path_used_when_provided(self, tmp_path):
        pm = self._pm_with_matches()
        out = tmp_path / 'out.bat'
        pm.export_to_batch(output_path=str(out))
        assert out.exists()

    def test_prompts_before_overwrite(self, tmp_path):
        pm = self._pm_with_matches()
        out = tmp_path / 'out.bat'
        out.write_text('old content')
        # User confirms overwrite
        with patch('builtins.input', return_value='y'):
            result = pm.export_to_batch(output_path=str(out))
        assert result is True
        assert 'choco install' in out.read_text()

    def test_cancels_on_no(self, tmp_path):
        pm = self._pm_with_matches()
        out = tmp_path / 'out.bat'
        out.write_text('old content')
        with patch('builtins.input', return_value='n'):
            result = pm.export_to_batch(output_path=str(out))
        assert result is False
        assert out.read_text() == 'old content'


# ---------------------------------------------------------------------------
# Issue #8 -- argparse
# ---------------------------------------------------------------------------

class TestArgParser:
    def test_auto_flag_parsed(self):
        from register_unmanaged_apps import _build_arg_parser
        args = _build_arg_parser().parse_args(['--auto'])
        assert args.auto is True

    def test_dry_run_flag_parsed(self):
        from register_unmanaged_apps import _build_arg_parser
        args = _build_arg_parser().parse_args(['--dry-run'])
        assert args.dry_run is True

    def test_export_only_flag_parsed(self):
        from register_unmanaged_apps import _build_arg_parser
        args = _build_arg_parser().parse_args(['--export-only'])
        assert args.export_only is True

    def test_min_score_parsed(self):
        from register_unmanaged_apps import _build_arg_parser
        args = _build_arg_parser().parse_args(['--min-score', '75'])
        assert args.min_score == 75

    def test_exclude_microsoft_parsed(self):
        from register_unmanaged_apps import _build_arg_parser
        args = _build_arg_parser().parse_args(['--exclude-microsoft'])
        assert args.exclude_microsoft is True


# ---------------------------------------------------------------------------
# Issue #7 -- dry-run flag
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_skips_choco_install(self):
        pm = PackageManager(dry_run=True)
        pm.matches = [{'app_name': 'Git', 'choco_id': 'git', 'app_version': '2.44', 'choco_version': '2.44'}]
        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return '', '', 0

        with patch.object(PackageManager, 'run_command', side_effect=fake_run):
            pm._register_packages(pm.matches)

        install_cmds = [c for c in captured_cmds if 'install' in c]
        assert install_cmds == [], 'choco install should not run in dry-run mode'

    def test_dry_run_reports_success(self):
        pm = PackageManager(dry_run=True)
        pm.matches = [{'app_name': 'Git', 'choco_id': 'git', 'app_version': '2.44', 'choco_version': '2.44'}]
        result = pm._register_packages(pm.matches)
        assert result is True


# ---------------------------------------------------------------------------
# Issue #13 -- logging infrastructure
# ---------------------------------------------------------------------------

class TestLogging:
    def test_quiet_flag_suppresses_info(self):
        from register_unmanaged_apps import _configure_logging
        import logging as _logging
        _configure_logging(quiet=True, log_file=None)
        assert _logging.getLogger().level == _logging.WARNING

    def test_normal_mode_shows_info(self):
        from register_unmanaged_apps import _configure_logging
        import logging as _logging
        # Reset then configure at INFO level
        _logging.getLogger().handlers.clear()
        _configure_logging(quiet=False, log_file=None)
        assert _logging.getLogger().level == _logging.INFO


# ---------------------------------------------------------------------------
# Issue #10 -- Scoop integration
# ---------------------------------------------------------------------------

class TestScoopPackages:
    def test_scoop_not_installed_returns_true(self):
        pm = PackageManager()
        with patch.object(PackageManager, 'run_command', return_value=('', 'not found', 1)):
            result = pm.get_scoop_packages()
        assert result is True
        assert len(pm.scoop_packages) == 0

    def test_scoop_packages_parsed(self):
        pm = PackageManager()
        scoop_output = 'Name  Version  Source\n----  -------  ------\ngit   2.44.0   main\nvscode 1.89   extras\n'
        with patch.object(PackageManager, 'run_command', return_value=(scoop_output, '', 0)):
            pm.get_scoop_packages()
        assert 'git' in pm.scoop_packages
        assert 'vscode' in pm.scoop_packages

    def test_scoop_apps_excluded_from_unmanaged(self):
        pm = PackageManager()
        pm.scoop_packages = {'git'}
        pm.choco_packages = set()
        pm.winget_apps = {}
        pm.installed_programs = [{'DisplayName': 'git', 'DisplayVersion': '2.44', 'Publisher': 'X'}]
        pm.find_unmanaged_apps()
        assert all(app['name'].lower() != 'git' for app in pm.unmanaged_apps)


# ---------------------------------------------------------------------------
# Issue #9 -- Version comparison
# ---------------------------------------------------------------------------

class TestVersionComparison:
    def test_same_major_version_no_mismatch(self):
        assert PackageManager._versions_differ('2.44.0', '2.3.0') is False

    def test_different_major_version_is_mismatch(self):
        assert PackageManager._versions_differ('1.9.0', '2.0.0') is True

    def test_unknown_version_no_mismatch(self):
        assert PackageManager._versions_differ('Unknown', '2.0.0') is False

    def test_empty_version_no_mismatch(self):
        assert PackageManager._versions_differ('', '2.0.0') is False

    def test_version_mismatch_flag_set_in_match(self):
        pm = PackageManager()
        pm.unmanaged_apps = [{'name': 'Git', 'version': '1.9.0'}]

        def fake_run(cmd, **kwargs):
            if '--exact' in cmd:
                return 'git|2.0.0\n', '', 0
            return '', '', 1

        with patch.object(PackageManager, 'run_command', side_effect=fake_run):
            with patch.object(PackageManager, 'get_choco_major_version', return_value=1):
                with patch('time.sleep'):
                    pm.search_chocolatey_matches()

        assert pm.matches, 'Expected at least one match'
        assert pm.matches[0]['version_mismatch'] is True

    def test_version_match_flag_not_set(self):
        pm = PackageManager()
        pm.unmanaged_apps = [{'name': 'Git', 'version': '2.44.0'}]

        def fake_run(cmd, **kwargs):
            if '--exact' in cmd:
                return 'git|2.0.0\n', '', 0
            return '', '', 1

        with patch.object(PackageManager, 'run_command', side_effect=fake_run):
            with patch.object(PackageManager, 'get_choco_major_version', return_value=1):
                with patch('time.sleep'):
                    pm.search_chocolatey_matches()

        assert pm.matches
        assert pm.matches[0]['version_mismatch'] is False


# ---------------------------------------------------------------------------
# Issue #11 -- JSON cache
# ---------------------------------------------------------------------------

class TestCache:
    def test_save_and_load_roundtrip(self, tmp_path):
        pm = PackageManager()
        pm.unmanaged_apps = [{'name': 'Git', 'version': '2.44'}]
        pm.matches = [{'app_name': 'Git', 'choco_id': 'git', 'version_mismatch': False}]
        cache_file = str(tmp_path / 'state.json')
        pm.save_cache(cache_file)

        pm2 = PackageManager()
        result = pm2.load_cache(cache_file)
        assert result is True
        assert pm2.matches == pm.matches
        assert pm2.unmanaged_apps == pm.unmanaged_apps

    def test_load_missing_cache_returns_false(self, tmp_path):
        pm = PackageManager()
        result = pm.load_cache(str(tmp_path / 'nonexistent.json'))
        assert result is False

    def test_cache_file_has_timestamp(self, tmp_path):
        pm = PackageManager()
        pm.matches = []
        pm.unmanaged_apps = []
        cache_file = str(tmp_path / 'state.json')
        pm.save_cache(cache_file)
        with open(cache_file) as f:
            data = json.load(f)
        assert 'timestamp' in data

    def test_use_cache_argparse_flag(self):
        from register_unmanaged_apps import _build_arg_parser
        args = _build_arg_parser().parse_args(['--use-cache'])
        assert args.use_cache is True
