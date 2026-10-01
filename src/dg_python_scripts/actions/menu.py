"""Serialize registered actions into Flame custom UI action groups."""

from typing import Any

from .registry import ACTION_CONTEXTS, ActionRegistry


def build_menu(
    registry: ActionRegistry,
    context: str,
    caption: str = "DGpy",
) -> tuple[dict[str, Any], ...]:
    if context not in ACTION_CONTEXTS:
        raise ValueError(f"Unknown action context: {context}")

    items = tuple(action.as_menu_item() for action in registry.actions(context))
    return ({"name": caption, "actions": items},) if items else ()
