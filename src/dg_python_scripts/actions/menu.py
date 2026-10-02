"""Serialize registered actions into Flame custom UI action groups."""

from collections import OrderedDict
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

    root_items: list[dict[str, Any]] = []
    default_items: list[dict[str, Any]] = []
    explicit_hierarchies: OrderedDict[
        tuple[str, ...], list[dict[str, Any]]
    ] = OrderedDict()

    for action in registry.actions(context):
        item = broker.bind(action, context)
        if action.hierarchy == ():
            root_items.append(item)
        elif action.hierarchy is None:
            default_items.append(item)
        else:
            explicit_hierarchies.setdefault(action.hierarchy, []).append(item)

    groups: list[dict[str, Any]] = []

    # Flame 2023.2+ supports anonymous groups with hierarchy=[]; actions in
    # these groups are placed directly in the host menu rather than a submenu.
    if root_items:
        groups.append(
            {
                "hierarchy": [],
                "actions": tuple(root_items),
            }
        )

    # Default DGpy actions remain grouped under the configured menu caption.
    if default_items:
        groups.append(
            {
                "name": caption,
                "hierarchy": [],
                "separator": "below",
                "actions": tuple(default_items),
            }
        )

    # Explicit hierarchy is available to extensions that want actions placed
    # directly inside a host hierarchy path.
    for hierarchy, items in explicit_hierarchies.items():
        groups.append(
            {
                "hierarchy": list(hierarchy),
                "actions": tuple(items),
            }
        )

    return tuple(groups)
