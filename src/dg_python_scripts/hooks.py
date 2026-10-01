"""Thick package entry points for the thin Flame bootstrap."""

from .actions.main_menu import register_builtin_actions
from .actions.menu import build_menu
from .actions.registry import ActionRegistry
from .config.loader import load_config

_registry: ActionRegistry | None = None


def get_registry() -> ActionRegistry:
    """Explicit extension seam; call on Flame's main thread before menu build."""
    global _registry
    if _registry is None:
        registry = ActionRegistry()
        register_builtin_actions(registry)
        _registry = registry
    return _registry


def _get_custom_ui_actions(context: str) -> tuple:
    config = load_config()
    return build_menu(get_registry(), context, config.menu_caption)


def get_main_menu_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("main_menu")


def get_media_panel_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("media_panel")


def get_timeline_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("timeline")


def get_batch_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("batch")


def get_action_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("action")
