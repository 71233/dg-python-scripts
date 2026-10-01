"""The only DGpy file deployed into Flame's Python Hook search path."""

import logging


def get_main_menu_custom_ui_actions():
    """Delegate to Core; a broken install must not break other Flame hooks."""
    try:
        from dgpy.hooks import get_main_menu_custom_ui_actions as build_menu

        return build_menu()
    except Exception:
        logging.getLogger("dgpy.bootstrap").exception(
            "DGpy menu unavailable. Check package installation/PYTHONPATH."
        )
        return ()
