"""The only DGpy file deployed into Flame's Python Hook search path."""

import logging


def _delegate(hook_name):
    """Delegate one Flame hook; a broken DGpy install must not break other hooks."""
    try:
        from dg_python_scripts import hooks

        return getattr(hooks, hook_name)()
    except Exception:
        logging.getLogger("dgpy.bootstrap").exception(
            "DGpy hook %s unavailable. Check package installation/PYTHONPATH.",
            hook_name,
        )
        return ()


def get_main_menu_custom_ui_actions():
    return _delegate("get_main_menu_custom_ui_actions")


def get_media_panel_custom_ui_actions():
    return _delegate("get_media_panel_custom_ui_actions")


def get_timeline_custom_ui_actions():
    return _delegate("get_timeline_custom_ui_actions")


def get_batch_custom_ui_actions():
    return _delegate("get_batch_custom_ui_actions")


def get_action_custom_ui_actions():
    return _delegate("get_action_custom_ui_actions")
