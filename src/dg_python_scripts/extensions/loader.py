"""Load configured extension modules without coupling Core to their names."""

import importlib
import logging

from dg_python_scripts.actions.registry import ActionRegistry

_LOG = logging.getLogger("dgpy.extensions")


class ExtensionContractError(RuntimeError):
    """Raised when a configured extension does not implement the DGpy contract."""


def load_extensions(
    module_names: tuple[str, ...],
    registry: ActionRegistry,
) -> tuple[str, ...]:
    """Load extensions independently and merge each extension atomically."""
    loaded: list[str] = []

    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
            register = getattr(module, "register", None)
            if not callable(register):
                raise ExtensionContractError(
                    f"{module_name!r} must define callable register(registry)"
                )

            staging = ActionRegistry()
            register(staging)
            registry.register_many(staging.actions())
        except Exception:
            _LOG.exception("DGpy extension failed to load: %s", module_name)
            continue

        loaded.append(module_name)

    return tuple(loaded)
