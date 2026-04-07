"""Abstract base classes for package manager adapters.

Every adapter (WinGet, Chocolatey, Scoop, or future additions) must implement
``BasePackageManager``.  Adapters with a searchable remote repository additionally
implement ``SearchablePackageManager``.  Adapters that can also install packages
implement ``InstallablePackageManager``.

Adding a new adapter requires only creating the adapter module — no changes to
``detector.py``, ``runner.py``, or any other orchestration code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class PackageMatch:
    """A resolved mapping between an installed display name and a package-repo entry."""

    app_name: str
    app_version: str
    pkg_id: str
    pkg_version: str
    version_mismatch: bool
    manager: str  # e.g. "chocolatey", "winget", "scoop"


@dataclass(frozen=True)
class AppCandidates:
    """All package-repo candidates for a single unmanaged app.

    *primary* is the highest-preference match (driven by ``MANAGER_PREFERENCE``).
    *alternatives* are the remaining matches, ordered by preference.
    """

    app_name: str
    app_version: str
    primary: PackageMatch
    alternatives: list[PackageMatch] = field(default_factory=list)

    @property
    def all_matches(self) -> list[PackageMatch]:
        """Primary first, then alternatives."""
        return [self.primary] + list(self.alternatives)


class BasePackageManager(ABC):
    """Minimum contract every adapter must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short human-readable identifier, e.g. ``'winget'``, ``'chocolatey'``."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the tool is installed and reachable on PATH.

        Must **never** raise; return ``False`` on any subprocess error.
        """

    @abstractmethod
    def list_managed(self) -> set[str]:
        """Return the set of *normalised* package names this manager owns."""

    @abstractmethod
    def is_managed(self, display_name: str) -> bool:
        """Return True if *display_name* (raw registry string) is managed here."""


class SearchablePackageManager(BasePackageManager, ABC):
    """Extended contract for managers whose repository can be searched."""

    @abstractmethod
    def search(self, app_name: str) -> Optional[PackageMatch]:
        """Search the repository for *app_name*.

        Returns a :class:`PackageMatch` on success, ``None`` otherwise.
        **Never raises** — return ``None`` on any subprocess or network error.
        """

    @abstractmethod
    def search_many(
        self,
        apps: list[dict],
        *,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        on_result: Optional[Callable[[str, Optional["PackageMatch"]], None]] = None,
    ) -> list[PackageMatch]:
        """Batch search with optional per-item callbacks."""


class InstallablePackageManager(SearchablePackageManager, ABC):
    """Full contract: search the repo **and** install packages from it."""

    @abstractmethod
    def install(self, match: PackageMatch, *, dry_run: bool = False) -> bool:
        """Install the package identified by *match*.

        Args:
            match: The resolved package to install.
            dry_run: When *True*, log what would be done but do not execute.

        Returns:
            ``True`` on success (or dry-run), ``False`` on failure.
        **Never raises.**
        """
