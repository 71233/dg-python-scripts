"""Thick package entry point for the thin Flame bootstrap."""

from .actions.main_menu import build_main_menu, register_builtin_actions
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


def get_main_menu_custom_ui_actions() -> tuple:
    config = load_config()
    return build_main_menu(get_registry(), config.menu_caption)
