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

        Installing via the package manager is also the adoption mechanism: after
        a successful install the manager writes its own tracking metadata (e.g.
        ``Source: winget`` in ``winget list``, or a Chocolatey lib entry), so
        subsequent scans will classify the app as managed by this manager.

        Args:
            match: The resolved package to install.
            dry_run: When *True*, log what would be done but do not execute.

        Returns:
            ``True`` on success (or dry-run), ``False`` on failure.
        **Never raises.**
        """

    @abstractmethod
    def refresh_cache(self) -> None:
        """Invalidate internal caches so the next ``is_managed()`` call re-queries
        the manager's live package list.

        Must be called after a successful :meth:`install` so that the app is
        immediately visible as managed without requiring a full re-scan.
        **Never raises.**
        """


def rank_candidates(
    all_results: dict[str, list[PackageMatch]],
    preference: list[str],
    prefer_override: Optional[str] = None,
) -> list[AppCandidates]:
    """Rank per-app multi-manager results into :class:`AppCandidates` list.

    Args:
        all_results: Mapping of ``app_name`` → list of :class:`PackageMatch`
            objects from different managers.
        preference: Ordered manager names — index 0 is highest priority.
        prefer_override: When set, move this manager to the front of the order.

    Returns:
        List of :class:`AppCandidates`, one per app that had at least one match.
    """
    order = list(preference)
    if prefer_override and prefer_override in order:
        order.remove(prefer_override)
        order.insert(0, prefer_override)
    elif prefer_override and prefer_override not in order:
        order.insert(0, prefer_override)

    candidates: list[AppCandidates] = []
    for app_name, matches in all_results.items():
        if not matches:
            continue
        # Group by manager name
        by_manager: dict[str, PackageMatch] = {}
        for m in matches:
            if m.manager not in by_manager:
                by_manager[m.manager] = m

        # Pick primary according to preference order
        primary: Optional[PackageMatch] = None
        for mgr_name in order:
            if mgr_name in by_manager:
                primary = by_manager[mgr_name]
                break
        # Fallback: first match in insertion order
        if primary is None:
            primary = matches[0]

        alternatives = [m for m in by_manager.values() if m is not primary]
        # Preserve preference order in alternatives too
        alternatives.sort(key=lambda m: order.index(m.manager) if m.manager in order else 999)

        candidates.append(
            AppCandidates(
                app_name=primary.app_name,
                app_version=primary.app_version,
                primary=primary,
                alternatives=alternatives,
            )
        )
    return candidates
