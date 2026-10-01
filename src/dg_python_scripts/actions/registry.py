"""Ordered, context-aware action registry for Flame custom UI hooks."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ACTION_CONTEXTS = frozenset(
    {"main_menu", "media_panel", "timeline", "batch", "action"}
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

    def as_menu_item(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "name": self.id,
            "caption": self.caption,
            "execute": self.execute,
        }
        if self.order is not None:
            item["order"] = self.order
        if self.minimum_version is not None:
            item["minimumVersion"] = self.minimum_version
        return item


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        if action.id in self._actions:
            raise ValueError(f"Duplicate action id: {action.id}")
        self._actions[action.id] = action

    def actions(self, context: str | None = None) -> tuple[Action, ...]:
        if context is None:
            return tuple(self._actions.values())
        if context not in ACTION_CONTEXTS:
            raise ValueError(f"Unknown action context: {context}")
        return tuple(
            action for action in self._actions.values() if context in action.contexts
        )
