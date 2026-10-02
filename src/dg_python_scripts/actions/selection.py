"""Bind Flame action callbacks to a stable predicate-selection policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .registry import Action


@dataclass(frozen=True)
class _SelectionSnapshot:
    selection: tuple[Any, ...]
    selected_at_capture: tuple[bool | None, ...]


def _as_tuple(selection: Any) -> tuple[Any, ...]:
    try:
        return tuple(selection)
    except Exception:
        return ()


def _selected_state(obj: Any) -> bool | None:
    try:
        value = getattr(obj, "selected")
    except Exception:
        return None

    getter = getattr(value, "get_value", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            return None

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        return bool(value)
    except Exception:
        return None


def _same_members(
    left: tuple[Any, ...],
    right: tuple[Any, ...],
) -> bool:
    if len(left) != len(right):
        return False
    return {id(item) for item in left} == {id(item) for item in right}


class SelectionBroker:
    """Prefer predicate selection while rejecting stale shortcut snapshots.

    Flame 2025.2.7 can pass a context-menu target to isVisible/isEnabled and a
    different global selection to execute.  A context target can legitimately
    be unselected (for example a Reel right-click while Clips remain selected).

    Keyboard shortcuts can also execute later with a stale predicate snapshot.
    The measured distinction is:
      * same members -> predicate selection is safe and preserves menu ordering;
      * predicate contains an item that was unselected at capture -> explicit
        context-menu target, so prefer the predicate selection;
      * otherwise a mismatch is treated as stale and execute selection wins.

    Snapshots are one-shot and are overwritten by the next predicate callback.
    No time-to-live heuristic is used.
    """

    def __init__(self):
        self._snapshots: dict[tuple[str, int], _SelectionSnapshot] = {}
        self._bindings: dict[tuple[str, int], dict[str, Any]] = {}

    def _key(self, action: "Action", context: str) -> tuple[str, int]:
        return context, id(action)

    def capture(self, key: tuple[str, int], selection: Any) -> tuple[Any, ...]:
        items = _as_tuple(selection)
        self._snapshots[key] = _SelectionSnapshot(
            selection=items,
            selected_at_capture=tuple(_selected_state(item) for item in items),
        )
        return items

    def resolve(
        self,
        key: tuple[str, int],
        execute_selection: Any,
    ) -> tuple[Any, ...]:
        executed = _as_tuple(execute_selection)
        snapshot = self._snapshots.pop(key, None)
        if snapshot is None:
            return executed

        if _same_members(snapshot.selection, executed):
            return snapshot.selection

        if any(state is False for state in snapshot.selected_at_capture):
            return snapshot.selection

        return executed

    def bind(self, action: "Action", context: str) -> dict[str, Any]:
        key = self._key(action, context)
        cached = self._bindings.get(key)
        if cached is not None:
            return dict(cached)

        def is_visible(selection):
            items = self.capture(key, selection)
            predicate = action.is_visible
            return True if predicate is None else bool(predicate(items))

        def is_enabled(selection):
            items = self.capture(key, selection)
            predicate = action.is_enabled
            return True if predicate is None else bool(predicate(items))

        def execute(selection):
            return action.execute(self.resolve(key, selection))

        item = action.as_menu_item()
        item["isVisible"] = is_visible
        item["isEnabled"] = is_enabled
        item["execute"] = execute
        self._bindings[key] = item
        return dict(item)
