"""Register the built-in DGpy Delete Markers action."""

from .registry import Action, ActionRegistry
from dg_python_scripts.markers import (
    MarkerApplyError,
    MarkerDeleteError,
    apply_delete_plan,
    build_delete_plan,
    can_delete_markers_selection,
)


_MARKER_CONTEXTS = ("media_panel",)


def _marker_action_available(selection) -> bool:
    return can_delete_markers_selection(selection)


def _show_dialog(flame, title: str, message: str, dialog_type: str, buttons, cancel_button=""):
    return flame.messages.show_in_dialog(
        title,
        message,
        dialog_type,
        list(buttons),
        cancel_button,
    )


def show_delete_markers(selection=()) -> None:
    import flame

    try:
        plan = build_delete_plan(selection)
    except MarkerDeleteError as error:
        _show_dialog(
            flame,
            "DGpy Delete Markers",
            str(error),
            "error",
            ("OK",),
        )
        return

    if not plan.targets:
        flame.messages.show_in_console(
            "DGpy: No Clip or Sequence targets found.",
            "info",
            4,
        )
        return

    if not plan.total_markers:
        flame.messages.show_in_console(
            f"DGpy: No markers found in {len(plan.targets)} Clip/Sequence target(s).",
            "info",
            4,
        )
        return

    marker_label = "marker" if plan.total_markers == 1 else "markers"
    answer = _show_dialog(
        flame,
        "DGpy Delete Markers",
        (
            f"Delete {plan.total_markers} {marker_label}?\n\n"
            "This action cannot be undone."
        ),
        "warning",
        ("Delete Markers",),
        "Cancel",
    )
    if answer != "Delete Markers":
        return

    try:
        result = apply_delete_plan(
            plan,
            lambda marker: flame.delete(marker, confirm=False),
        )
    except MarkerApplyError as error:
        _show_dialog(
            flame,
            "DGpy Delete Markers",
            f"{error}\n\nDeleted before failure: {error.deleted}",
            "error",
            ("OK",),
        )
        return

    flame.messages.show_in_console(
        (
            f"DGpy: Deleted {result.deleted} marker(s) from "
            f"{result.changed_targets} Clip/Sequence target(s)."
        ),
        "info",
        5,
    )


def register_delete_markers_action(registry: ActionRegistry) -> None:
    registry.register(
        Action(
            "dgpy.delete_markers",
            "Delete Markers",
            show_delete_markers,
            contexts=_MARKER_CONTEXTS,
            order=110,
            is_visible=_marker_action_available,
            is_enabled=_marker_action_available,
            hierarchy=("DGpy Sequence",),
            wait_cursor=False,
            separator=None,
        )
    )
