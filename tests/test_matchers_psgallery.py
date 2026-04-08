"""Tests for src/wincoman/matchers/psgallery.py — PSGallery module detection."""
from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from wincoman.matchers.psgallery import PSGalleryManager


def _make_clixml(name: str, repository: str = "PSGallery", version: str = "1.0.0") -> bytes:
    """Return a minimal PSGetModuleInfo.xml as UTF-16 LE bytes (matches real PowerShell output)."""
    content = (
        '<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">\n'
        '  <Obj RefId="0">\n'
        f'    <S N="Name">{name}</S>\n'
        f'    <S N="Version">{version}</S>\n'
        f'    <S N="Repository">{repository}</S>\n'
        "  </Obj>\n"
        "</Objs>\n"
    )
    return codecs.BOM_UTF16_LE + content.encode("utf-16-le")


def _write_marker(tmp_path: Path, module_name: str, repository: str = "PSGallery") -> Path:
    """Write a PSGetModuleInfo.xml under tmp_path/<module_name>/1.0.0/ and return the path."""
    marker_dir = tmp_path / module_name / "1.0.0"
    marker_dir.mkdir(parents=True)
    marker = marker_dir / "PSGetModuleInfo.xml"
    marker.write_bytes(_make_clixml(module_name, repository=repository))
    return marker


class TestPSGalleryManagerAvailability:
    def test_available_when_module_path_exists(self, tmp_path: Path):
        mgr = PSGalleryManager(module_paths=[tmp_path])
        assert mgr.is_available() is True

    def test_unavailable_when_no_path_exists(self, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist"
        mgr = PSGalleryManager(module_paths=[nonexistent])
        assert mgr.is_available() is False

    def test_available_cached_after_first_call(self, tmp_path: Path):
        mgr = PSGalleryManager(module_paths=[tmp_path])
        mgr.is_available()
        mgr.is_available()  # second call must not re-scan


class TestPSGalleryManagerListManaged:
    def test_finds_psgallery_module(self, tmp_path: Path):
        _write_marker(tmp_path, "Microsoft.WinGet.Client")
        mgr = PSGalleryManager(module_paths=[tmp_path])
        managed = mgr.list_managed()
        assert "microsoftwingetclient" in managed  # normalized form

    def test_excludes_non_psgallery_module(self, tmp_path: Path):
        _write_marker(tmp_path, "PrivateModule", repository="InternalFeed")
        mgr = PSGalleryManager(module_paths=[tmp_path])
        managed = mgr.list_managed()
        assert "privatemodule" not in managed
        assert len(managed) == 0

    def test_multiple_modules(self, tmp_path: Path):
        _write_marker(tmp_path, "Microsoft.WinGet.Client")
        _write_marker(tmp_path, "PSWindowsUpdate")
        mgr = PSGalleryManager(module_paths=[tmp_path])
        managed = mgr.list_managed()
        assert "microsoftwingetclient" in managed
        assert "pswindowsupdate" in managed

    def test_empty_when_no_markers(self, tmp_path: Path):
        mgr = PSGalleryManager(module_paths=[tmp_path])
        assert mgr.list_managed() == set()

    def test_cache_populated_on_first_call(self, tmp_path: Path):
        _write_marker(tmp_path, "PSWindowsUpdate")
        mgr = PSGalleryManager(module_paths=[tmp_path])
        mgr.list_managed()
        assert mgr._cache is not None


class TestPSGalleryManagerIsManaged:
    def test_is_managed_exact_name(self, tmp_path: Path):
        _write_marker(tmp_path, "Microsoft.WinGet.Client")
        mgr = PSGalleryManager(module_paths=[tmp_path])
        assert mgr.is_managed("Microsoft.WinGet.Client") is True

    def test_is_managed_normalized(self, tmp_path: Path):
        _write_marker(tmp_path, "Microsoft.WinGet.Client")
        mgr = PSGalleryManager(module_paths=[tmp_path])
        assert mgr.is_managed("MicrosoftWinGetClient") is True

    def test_not_managed_unknown(self, tmp_path: Path):
        _write_marker(tmp_path, "PSWindowsUpdate")
        mgr = PSGalleryManager(module_paths=[tmp_path])
        assert mgr.is_managed("CompletelyUnknownModule") is False


class TestReadModuleName:
    def test_reads_utf16_clixml(self, tmp_path: Path):
        xml = tmp_path / "PSGetModuleInfo.xml"
        xml.write_bytes(_make_clixml("TestModule", repository="PSGallery"))
        result = PSGalleryManager._read_module_name(xml)
        assert result == "TestModule"

    def test_returns_none_for_non_psgallery(self, tmp_path: Path):
        xml = tmp_path / "PSGetModuleInfo.xml"
        xml.write_bytes(_make_clixml("PrivateModule", repository="InternalRepo"))
        result = PSGalleryManager._read_module_name(xml)
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path: Path):
        xml = tmp_path / "nonexistent.xml"
        result = PSGalleryManager._read_module_name(xml)
        assert result is None

    def test_reads_utf8_clixml(self, tmp_path: Path):
        """Falls back to UTF-8 for modules not exported with UTF-16."""
        content = (
            '<Objs Version="1.1.0.1">\n'
            '  <S N="Name">Utf8Module</S>\n'
            '  <S N="Repository">PSGallery</S>\n'
            "</Objs>\n"
        )
        xml = tmp_path / "PSGetModuleInfo.xml"
        xml.write_text(content, encoding="utf-8")
        result = PSGalleryManager._read_module_name(xml)
        assert result == "Utf8Module"
