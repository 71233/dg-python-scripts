"""Ordered, context-aware action registry for Flame custom UI hooks."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ACTION_CONTEXTS = frozenset(
    {"main_menu", "media_panel", "mediahub_files", "mediahub_archives", "timeline", "batch", "action"}
)
DEFAULT_CONTEXTS = ("main_menu",)


@dataclass(frozen=True)
class Action:
    id: str
    caption: str
    execute: Callable[[tuple[Any, ...]], None]
    contexts: tuple[str, ...] = DEFAULT_CONTEXTS
    order: int | None = None
    minimum_version: str | None = None
    flame_name: str | None = None
    is_visible: Callable[[tuple[Any, ...]], bool] | None = None
    is_enabled: Callable[[tuple[Any, ...]], bool] | None = None
    hierarchy: tuple[str, ...] | None = None
    wait_cursor: bool | None = None

    def __post_init__(self):
        if not self.id.strip() or not self.caption.strip():
            raise ValueError("Action id and caption must not be empty")
        if not callable(self.execute):
            raise TypeError("Action execute must be callable")

        contexts = tuple(dict.fromkeys(self.contexts))
        if not contexts:
            raise ValueError("Action must target at least one context")
        unknown = set(contexts) - ACTION_CONTEXTS
        if unknown:
            raise ValueError(f"Unknown action contexts: {sorted(unknown)}")
        object.__setattr__(self, "contexts", contexts)

        if self.order is not None and (
            isinstance(self.order, bool) or not isinstance(self.order, int)
        ):
            raise TypeError("Action order must be an integer or None")
        if self.minimum_version is not None and (
            not isinstance(self.minimum_version, str)
            or not self.minimum_version.strip()
        ):
            raise ValueError("minimum_version must be a non-empty string or None")
        if self.flame_name is not None and (
            not isinstance(self.flame_name, str) or not self.flame_name.strip()
        ):
            raise ValueError("flame_name must be a non-empty string or None")
        if self.is_visible is not None and not callable(self.is_visible):
            raise TypeError("is_visible must be callable or None")
        if self.is_enabled is not None and not callable(self.is_enabled):
            raise TypeError("is_enabled must be callable or None")
        if self.hierarchy is not None:
            hierarchy = tuple(self.hierarchy)
            if any(not isinstance(part, str) or not part.strip() for part in hierarchy):
                raise ValueError("hierarchy entries must be non-empty strings")
            object.__setattr__(self, "hierarchy", hierarchy)
        if self.wait_cursor is not None and not isinstance(self.wait_cursor, bool):
            raise TypeError("wait_cursor must be a bool or None")

    @property
    def host_name(self) -> str:
        """Name exposed to Flame; defaults to the visible caption."""
        return self.flame_name or self.caption

    def as_menu_item(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "name": self.host_name,
            "caption": self.caption,
            "execute": self.execute,
        }
        if self.order is not None:
            item["order"] = self.order
        if self.minimum_version is not None:
            item["minimumVersion"] = self.minimum_version
        if self.is_visible is not None:
            item["isVisible"] = self.is_visible
        if self.is_enabled is not None:
            item["isEnabled"] = self.is_enabled
        if self.wait_cursor is not None:
            item["waitCursor"] = self.wait_cursor
        return item


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        if action.id in self._actions:
            raise ValueError(f"Duplicate action id: {action.id}")
        self._actions[action.id] = action

    def register_many(self, actions) -> None:
        pending = tuple(actions)
        identifiers = [action.id for action in pending]
        duplicates = sorted(
            identifier for identifier in set(identifiers)
            if identifiers.count(identifier) > 1
        )
        conflicts = sorted(set(identifiers) & set(self._actions))
        if duplicates:
            raise ValueError(f"Duplicate action ids in batch: {duplicates}")
        if conflicts:
            raise ValueError(f"Action ids already registered: {conflicts}")
        for action in pending:
            self._actions[action.id] = action

    def actions(self, context: str | None = None) -> tuple[Action, ...]:
        if context is None:
            return tuple(self._actions.values())
        if context not in ACTION_CONTEXTS:
            raise ValueError(f"Unknown action context: {context}")
        return tuple(
            action for action in self._actions.values() if context in action.contexts
        )
