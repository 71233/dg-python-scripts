"""Register the built-in DGpy Rename action."""

from .registry import Action, ActionRegistry
from dg_python_scripts.rename import can_rename_selection


_RENAME_CONTEXTS = (
    "media_panel",
    "timeline",
    "batch",
    "action",
)


def _rename_available(selection) -> bool:
    return can_rename_selection(selection)


def show_rename(selection=()) -> None:
    from dg_python_scripts.ui.rename import show_rename_dialog

    show_rename_dialog(selection)


def register_rename_action(registry: ActionRegistry) -> None:
    registry.register(
        Action(
            "dgpy.rename",
            "DGpy Rename...",
            show_rename,
            contexts=_RENAME_CONTEXTS,
            order=100,
            is_visible=_rename_available,
            is_enabled=_rename_available,
            hierarchy=(),
            wait_cursor=False,
            separator="above",
        )
    )
