"""Unmanaged-app detector.

:func:`find_unmanaged` cross-references the list of installed programs against
an ordered list of :class:`~wincoman.matchers.base.BasePackageManager` adapters.
Adding a new adapter requires **zero changes** to this module.
"""
from __future__ import annotations

from wincoman.matchers.base import BasePackageManager


def find_unmanaged(
    installed: list[dict],
    managers: list[BasePackageManager],
) -> list[dict]:
    """Return installed programs that are not claimed by any manager.

    Args:
        installed: Programs from the registry scan.  Each dict must have at
            least a ``DisplayName`` key.
        managers: Ordered list of adapters to consult.  A program is
            considered *managed* as soon as **any** adapter's
            :meth:`~BasePackageManager.is_managed` returns ``True``.

    Returns:
        List of dicts with keys ``name``, ``version``, ``publisher``,
        ``normalized`` for each unmanaged program.
    """
    from wincoman.scoring import normalize_name

    unmanaged: list[dict] = []
    for program in installed:
        display_name = program.get("DisplayName", "")
        if not display_name:
            continue

        if any(m.is_managed(display_name) for m in managers):
            continue

        unmanaged.append(
            {
                "name": display_name,
                "version": program.get("DisplayVersion", "Unknown"),
                "publisher": program.get("Publisher", "Unknown"),
                "normalized": normalize_name(display_name),
            }
        )
    return unmanaged
