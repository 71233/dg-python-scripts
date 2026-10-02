"""Built-in DGpy actions."""

from .registry import Action, ActionRegistry
from .rename_action import register_rename_action


def show_about(selection=()) -> None:
    # Qt is loaded only when the artist clicks the action.
    from dg_python_scripts.ui.about import show_about_dialog

    show_about_dialog()


def register_builtin_actions(registry: ActionRegistry) -> None:
    register_rename_action(registry)
    registry.register(
        Action(
            "dgpy.about",
            "About / Diagnostics",
            show_about,
            contexts=("main_menu",),
            order=1000,
        )
    )
