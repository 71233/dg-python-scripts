"""Thick package entry points for the thin Flame bootstrap."""

from .actions.main_menu import register_builtin_actions
from .actions.menu import build_menu
from .actions.registry import ActionRegistry
from .actions.selection import SelectionBroker
from .config.loader import Config, load_config
from .extensions.loader import load_extensions

_registry: ActionRegistry | None = None
_selection_broker = SelectionBroker()


def _get_registry(config: Config | None = None) -> ActionRegistry:
    global _registry
    if _registry is None:
        if config is None:
            config = load_config()

        registry = ActionRegistry()
        register_builtin_actions(registry)
        load_extensions(config.extensions.modules, registry)
        _registry = registry
    return _registry


def get_registry() -> ActionRegistry:
    """Return the process registry, creating it and configured extensions once."""
    return _get_registry()


def _get_custom_ui_actions(context: str) -> tuple:
    config = load_config()
    registry = _get_registry(config)
    return build_menu(
        registry,
        context,
        config.ui.menu_caption,
        broker=_selection_broker,
    )


def get_main_menu_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("main_menu")


def get_media_panel_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("media_panel")


def get_mediahub_files_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("mediahub_files")


def get_mediahub_archives_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("mediahub_archives")


def get_timeline_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("timeline")


def get_batch_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("batch")


def get_action_custom_ui_actions() -> tuple:
    return _get_custom_ui_actions("action")
