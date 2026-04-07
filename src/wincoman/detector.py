"""Unmanaged-app detector.

:func:`find_unmanaged` cross-references the list of installed programs against
an ordered list of :class:`~wincoman.matchers.base.BasePackageManager` adapters.
Adding a new adapter requires **zero changes** to this module.
"""
from __future__ import annotations

from typing import Callable, Optional

from wincoman.matchers.base import BasePackageManager

ClassifyCb = Callable[[str, Optional[str]], None]


def find_unmanaged(
    installed: list[dict],
    managers: list[BasePackageManager],
    *,
    on_classify: Optional[ClassifyCb] = None,
) -> list[dict]:
    """Return installed programs that are not claimed by any manager.

    Args:
        installed: Programs from the registry scan.  Each dict must have at
            least a ``DisplayName`` key.
        managers: Ordered list of adapters to consult.  A program is
            considered *managed* as soon as **any** adapter's
            :meth:`~BasePackageManager.is_managed` returns ``True``.
        on_classify: Optional callback invoked per program with
            ``(display_name, manager_name)`` when managed, or
            ``(display_name, None)`` when unmanaged.

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

        claimed_by: Optional[str] = None
        for m in managers:
            if m.is_managed(display_name):
                claimed_by = m.name
                break

        if on_classify is not None:
            on_classify(display_name, claimed_by)

        if claimed_by is not None:
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
