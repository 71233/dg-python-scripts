"""Serialize registered actions into Flame custom UI action groups."""

from typing import Any

from .registry import ACTION_CONTEXTS, ActionRegistry
from .selection import SelectionBroker


def build_menu(
    registry: ActionRegistry,
    context: str,
    caption: str = "DGpy",
    broker: SelectionBroker | None = None,
) -> tuple[dict[str, Any], ...]:
    if context not in ACTION_CONTEXTS:
        raise ValueError(f"Unknown action context: {context}")

    if broker is None:
        broker = SelectionBroker()

    items = tuple(
        broker.bind(action, context)
        for action in registry.actions(context)
    )
    return ({"name": caption, "actions": items},) if items else ()
