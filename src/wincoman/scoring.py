"""Fuzzy matching, name normalisation, and version comparison utilities.

All functions in this module are pure (no I/O, no subprocess calls) and can
be imported independently of any package-manager adapter.
"""
from __future__ import annotations

import re

try:
    from rapidfuzz import fuzz as _fuzz

    _RAPIDFUZZ_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RAPIDFUZZ_AVAILABLE = False


def normalize_name(name: str) -> str:
    """Normalise *name* for comparison.

    Strips version suffixes and non-alphanumeric characters, then
    lowercases the result.

    Examples::

        >>> normalize_name("Git 2.44.0")
        'git'
        >>> normalize_name("Google Chrome")
        'googlechrome'
    """
    if not name:
        return ""
    normalized = re.sub(r"\d+\.\d+.*", "", name)
    normalized = re.sub(r"[^a-z0-9]", "", normalized.lower())
    return normalized


def strip_version_suffix(name: str) -> str:
    """Strip trailing version-like suffixes from a display name.

    Useful for producing clean search queries from registry DisplayName values
    that embed version numbers (e.g. ``"HWiNFO64 7.28-4900"`` → ``"HWiNFO64"``).

    Only the trailing portion is removed; embedded version-like tokens are kept.

    Examples::

        >>> strip_version_suffix("HWiNFO64 7.28-4900")
        'HWiNFO64'
        >>> strip_version_suffix("Git 2.44.0")
        'Git'
        >>> strip_version_suffix("Google Chrome")
        'Google Chrome'
        >>> strip_version_suffix("Python 3.12.4 (64-bit)")
        'Python'
    """
    # Remove trailing version pattern: optional "v" + digit(s) + dots/dashes/underscores
    # Also strip anything after (e.g. "(64-bit)", "(x64)" that follows)
    stripped = re.sub(
        r"\s+v?\d[\d.\-_]*(\s*\(.*\))?\s*$",
        "",
        name.strip(),
        flags=re.IGNORECASE,
    )
    return stripped.strip() or name


def fuzzy_score(a: str, b: str) -> int:
    """Return a 0-100 similarity score between *a* and *b*.

    Uses ``rapidfuzz.fuzz.WRatio`` which handles partial matches, token
    reordering, and case differences.  Falls back to a binary 100/0 exact
    match on normalised names when rapidfuzz is not installed.
    """
    if _RAPIDFUZZ_AVAILABLE:
        return int(_fuzz.WRatio(a, b))
    # Fallback: exact match on normalised names
    na = re.sub(r"[^a-z0-9]", "", a.lower())
    nb = re.sub(r"[^a-z0-9]", "", b.lower())
    return 100 if na == nb else 0


def versions_differ(installed: str | None, choco: str | None) -> bool:
    """Return True if *installed* and *choco* differ at the major-version level.

    Both values are normalised to their leading numeric component.  If either
    is empty or unrecognised the comparison is skipped and ``False`` is
    returned.
    """

    def _major(ver) -> str:
        if ver is None:
            return ""
        ver = str(ver).strip()
        if not ver or ver.lower() in ("unknown", "n/a"):
            return ""
        parts = re.findall(r"\d+", ver)
        return parts[0] if parts else ""

    m_inst = _major(installed)
    m_choco = _major(choco)
    if not m_inst or not m_choco:
        return False
    return m_inst != m_choco
