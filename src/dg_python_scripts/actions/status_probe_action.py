"""Register the one-shot Status HUD data-source probe."""

from .registry import Action, ActionRegistry


def show_status_probe(selection=()) -> None:
    from dg_python_scripts.ui.status_probe import show_status_probe_dialog

    show_status_probe_dialog()


def register_status_probe_action(registry: ActionRegistry) -> None:
    registry.register(
        Action(
            "dgpy.status_probe",
            "Status HUD Probe...",
            show_status_probe,
            contexts=("main_menu",),
            order=900,
            minimum_version="2025.2.7",
            wait_cursor=False,
        )
    )
