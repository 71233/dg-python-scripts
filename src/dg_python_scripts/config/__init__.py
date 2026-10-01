"""DGpy Core configuration schema and TOML loader."""

from .loader import Config, ExtensionsConfig, UIConfig, load_config

__all__ = ["Config", "ExtensionsConfig", "UIConfig", "load_config"]
