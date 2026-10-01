"""Explicit TOML configuration for DGpy Core."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class UIConfig:
    menu_caption: str = "DGpy"


@dataclass(frozen=True)
class ExtensionsConfig:
    modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    ui: UIConfig = field(default_factory=UIConfig)
    extensions: ExtensionsConfig = field(default_factory=ExtensionsConfig)


def _reject_unknown(
    data: dict[str, Any],
    allowed: set[str],
    location: str,
) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown DGpy {location} keys: {sorted(unknown)}")


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"DGpy [{name}] must be a TOML table")
    return value


def _load_ui(data: dict[str, Any]) -> UIConfig:
    _reject_unknown(data, {"menu_caption"}, "[ui]")
    caption = data.get("menu_caption", "DGpy")
    if not isinstance(caption, str) or not caption.strip():
        raise ValueError("[ui].menu_caption must be a non-empty string")
    return UIConfig(menu_caption=caption)


def _valid_module_name(value: str) -> bool:
    return bool(value) and all(part.isidentifier() for part in value.split("."))


def _load_extensions(data: dict[str, Any]) -> ExtensionsConfig:
    _reject_unknown(data, {"modules"}, "[extensions]")
    modules = data.get("modules", [])
    if not isinstance(modules, list):
        raise ValueError("[extensions].modules must be an array of module names")
    if any(not isinstance(module, str) or not _valid_module_name(module) for module in modules):
        raise ValueError(
            "[extensions].modules entries must be valid dotted Python module names"
        )
    if len(set(modules)) != len(modules):
        raise ValueError("[extensions].modules must not contain duplicates")
    return ExtensionsConfig(modules=tuple(modules))


def load_config(path: str | Path | None = None) -> Config:
    """Load one explicit TOML file; path overrides DGPY_CONFIG."""
    location = path if path is not None else os.environ.get("DGPY_CONFIG")
    if not location:
        return Config()

    config_path = Path(location).expanduser()
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)

    _reject_unknown(data, {"ui", "extensions"}, "top-level")
    return Config(
        ui=_load_ui(_table(data, "ui")),
        extensions=_load_extensions(_table(data, "extensions")),
    )
