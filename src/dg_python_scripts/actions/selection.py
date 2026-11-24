"""Bind Flame action callbacks to a stable predicate-selection policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from .selection_contract import selection_item_is_primitive

if TYPE_CHECKING:
    from .registry import Action


class SelectionPredicateError(RuntimeError):
    """Dispatch stopped because a predicate is pending or previously failed."""


class SelectionInputError(ValueError):
    """A callback selection cannot be safely interpreted."""


@dataclass(frozen=True)
class _SelectionSnapshot:
    selection: tuple[Any, ...]
    selected_at_capture: tuple[bool | None, ...]


def _as_tuple(selection: Any) -> tuple[Any, ...]:
    # Flame documents a tuple. Retain plain-list compatibility without
    # executing arbitrary iterator methods or accepting scalar values.
    if type(selection) is tuple:
        items = selection
    elif type(selection) is list:
        items = tuple(selection)
    else:
        raise SelectionInputError("DGpy selection must be a plain tuple or list.")
    seen: set[int] = set()
    for item in items:
        if selection_item_is_primitive(item):
            raise SelectionInputError("DGpy selection contains an invalid item.")
        key = id(item)
        if key in seen:
            raise SelectionInputError("DGpy selection contains a duplicate object.")
        seen.add(key)
    return items


def _selected_state(obj: Any) -> bool | None:
    try:
        value = getattr(obj, "selected")
        getter = getattr(value, "get_value", None)
    except Exception:
        return None

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
    No time-to-live heuristic is used. A predicate exception invalidates
    its snapshot and blocks this binding until the failed phase returns
    True on a later evaluation. False alone retains legacy behavior.
    Both callback paths reject invalid shapes, primitive items and
    repeated Python identities. This is not host object authentication.
    This is a conservative failure policy, not host authorization.
    """

    def __init__(self):
        self._snapshots: dict[tuple[str, int], _SelectionSnapshot] = {}
        self._bindings: dict[tuple[str, int], dict[str, Any]] = {}
        self._evaluating: set[tuple[str, int]] = set()
        self._failed_predicates: dict[tuple[str, int], set[str]] = {}

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
        # Check before inspecting execute arguments or consuming anything.
        # A failed predicate must not fall through to a different target.
        if key in self._evaluating:
            raise SelectionPredicateError(
                "DGpy action blocked: predicate evaluation is in progress."
            )
        if key in self._failed_predicates:
            raise SelectionPredicateError(
                "DGpy action blocked: predicate evaluation failed; "
                "a new successful evaluation of the failed phase is required."
            )
        # An execute attempt consumes its snapshot even if its input is
        # invalid. Never use an old context target instead of bad input.
        snapshot = self._snapshots.pop(key, None)
        executed = _as_tuple(execute_selection)
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

        def evaluate(selection, predicate, phase):
            if key in self._evaluating:
                raise SelectionPredicateError(
                    "DGpy action blocked: predicate evaluation is already in progress."
                )
            self._evaluating.add(key)
            try:
                items = self.capture(key, selection)
                result = True if predicate is None else bool(predicate(items))
            except BaseException:
                # Cleanup only: preserve the original exception, including
                # interruptions. Do not retain failed or older selections.
                self._snapshots.pop(key, None)
                self._failed_predicates.setdefault(key, set()).add(phase)
                raise
            else:
                failed = self._failed_predicates.get(key)
                if failed is not None:
                    if result:
                        failed.discard(phase)
                    if failed:
                        # Another failed phase, or False, is not recovery.
                        self._snapshots.pop(key, None)
                    else:
                        self._failed_predicates.pop(key)
                return result
            finally:
                self._evaluating.remove(key)

        def is_visible(selection):
            return evaluate(selection, action.is_visible, "isVisible")

        def is_enabled(selection):
            return evaluate(selection, action.is_enabled, "isEnabled")

        def execute(selection):
            return action.execute(self.resolve(key, selection))

        item = action.as_menu_item()
        item["isVisible"] = is_visible
        item["isEnabled"] = is_enabled
        item["execute"] = execute
        self._bindings[key] = item
        return dict(item)
