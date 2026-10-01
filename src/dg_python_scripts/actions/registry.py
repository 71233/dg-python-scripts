"""Small, ordered action registry; no plugin discovery or private imports."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Action:
    id: str
    caption: str
    execute: Callable[[tuple[Any, ...]], None]

    def __post_init__(self):
        if not self.id.strip() or not self.caption.strip():
            raise ValueError("Action id and caption must not be empty")
        if not callable(self.execute):
            raise TypeError("Action execute must be callable")

    def as_menu_item(self) -> dict[str, Any]:
        return {"name": self.id, "caption": self.caption, "execute": self.execute}


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        if action.id in self._actions:
            raise ValueError(f"Duplicate action id: {action.id}")
        self._actions[action.id] = action

    def actions(self) -> tuple[Action, ...]:
        return tuple(self._actions.values())
