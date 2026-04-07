"""Abstract base classes for package manager adapters.

Every adapter (WinGet, Chocolatey, Scoop, or future additions) must implement
``BasePackageManager``.  Adapters with a searchable remote repository additionally
implement ``SearchablePackageManager``.

Adding a new adapter requires only creating the adapter module — no changes to
``detector.py``, ``runner.py``, or any other orchestration code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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


class BasePackageManager(ABC):
    """Minimum contract every adapter must satisfy.

    Implementing a new adapter requires only this file and the adapter
    module — no changes to ``detector.py`` or ``runner.py``.
    """

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
        """Return the set of *normalised* package names this manager owns.

        Normalisation must be consistent with :func:`wincoman.scoring.normalize_name`.
        Called once per scan; result may be cached by the adapter.
        """

    @abstractmethod
    def is_managed(self, display_name: str) -> bool:
        """Return True if *display_name* (raw registry string) is managed here.

        Implementations may use exact lookup first, then fuzzy fallback.
        Called once per installed program per manager.
        """


class SearchablePackageManager(BasePackageManager, ABC):
    """Extended contract for managers whose repository can be searched.

    Only managers with a remote/searchable catalogue need implement this.
    WinGet and Scoop use list-only adapters; Chocolatey implements this mixin.
    """

    @abstractmethod
    def search(self, app_name: str) -> Optional[PackageMatch]:
        """Search the repository for *app_name*.

        Returns a :class:`PackageMatch` if a candidate scores at or above the
        configured fuzzy threshold, otherwise ``None``.
        **Never raises** — return ``None`` on any subprocess or network error.
        """

    @abstractmethod
    def search_many(
        self,
        apps: list[dict],
        *,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> list[PackageMatch]:
        """Batch search with optional per-item progress callback.

        Default implementation loops over :meth:`search`;
        adapters may override for bulk API calls.
        """
