"""Tests for src/wincoman/shell.py (Issue #19)."""
import subprocess
from unittest.mock import MagicMock, patch

from wincoman.shell import DEFAULT_TIMEOUT, get_choco_major_version, run_command


class TestRunCommand:
    def test_returns_stdout_stderr_returncode(self):
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout="hello", stderr="", returncode=0),
        ):
            stdout, stderr, code = run_command(["echo", "hello"])
        assert stdout == "hello"
        assert code == 0

    def test_timeout_defaults_to_DEFAULT_TIMEOUT(self):
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout="", stderr="", returncode=0),
        ) as mock_run:
            run_command(["choco", "--version"])
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == DEFAULT_TIMEOUT

    def test_custom_timeout_respected(self):
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout="", stderr="", returncode=0),
        ) as mock_run:
            run_command(["choco", "--version"], timeout=5)
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 5

    def test_timeout_expired_returns_error_tuple(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["choco"], timeout=60),
        ):
            stdout, stderr, code = run_command(["choco", "search", "x"])
        assert stdout == ""
        assert "timed out" in stderr.lower()
        assert code == 1

    def test_file_not_found_returns_error_tuple(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            stdout, stderr, code = run_command(["nonexistent-binary"])
        assert stdout == ""
        assert "not found" in stderr.lower()
        assert code == 1

    def test_cmd_shim_uses_shell_true(self):
        """.cmd shims (e.g. scoop) must run with shell=True so cmd.exe interprets them."""
        with patch("shutil.which", return_value=r"C:\Users\user\scoop\shims\scoop.CMD"), \
             patch("subprocess.run",
                   return_value=MagicMock(stdout="ok", stderr="", returncode=0)) as mock_run:
            run_command(["scoop", "--version"])
        _, kwargs = mock_run.call_args
        assert kwargs["shell"] is True

    def test_bat_shim_uses_shell_true(self):
        """.bat files also need shell=True."""
        with patch("shutil.which", return_value=r"C:\tools\mytool.bat"), \
             patch("subprocess.run",
                   return_value=MagicMock(stdout="ok", stderr="", returncode=0)) as mock_run:
            run_command(["mytool", "--version"])
        _, kwargs = mock_run.call_args
        assert kwargs["shell"] is True

    def test_exe_does_not_force_shell_true(self):
        """Regular .exe executables should NOT use shell=True by default."""
        with patch("shutil.which", return_value=r"C:\tools\winget.EXE"), \
             patch("subprocess.run",
                   return_value=MagicMock(stdout="ok", stderr="", returncode=0)) as mock_run:
            run_command(["winget", "--version"])
        _, kwargs = mock_run.call_args
        assert kwargs["shell"] is False


class TestGetChocoMajorVersion:
    def test_parses_major_version(self):
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout="2.3.0\n", returncode=0),
        ):
            assert get_choco_major_version() == 2

    def test_returns_zero_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert get_choco_major_version() == 0

    def test_returns_zero_on_timeout(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["choco"], timeout=15),
        ):
            assert get_choco_major_version() == 0

    def test_v1_detected(self):
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout="1.4.0\n", returncode=0),
        ):
            assert get_choco_major_version() == 1
