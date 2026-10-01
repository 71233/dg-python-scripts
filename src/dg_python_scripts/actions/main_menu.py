"""Initial, read-only diagnostics action and Flame menu serialization."""

from .registry import Action, ActionRegistry


def show_about(selection=()) -> None:
    # Qt is loaded only when the artist clicks the action.
    from dg_python_scripts.ui.about import show_about_dialog

    show_about_dialog()


def register_builtin_actions(registry: ActionRegistry) -> None:
    registry.register(Action("dgpy.about", "About / Diagnostics", show_about))


def build_main_menu(registry: ActionRegistry, caption: str = "DGpy") -> tuple:
    items = tuple(action.as_menu_item() for action in registry.actions())
    return ({"name": caption, "actions": items},) if items else ()
