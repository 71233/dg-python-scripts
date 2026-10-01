"""Defaults plus one optional JSON file; no studio-specific locations."""

from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class Config:
    menu_caption: str = "DGpy"


def load_config(path: str | Path | None = None) -> Config:
    """Explicit path overrides DGPY_CONFIG; malformed/missing files raise."""
    location = path if path is not None else os.environ.get("DGPY_CONFIG")
    if not location:
        return Config()
    with Path(location).expanduser().open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("DGpy configuration must be a JSON object")
    unknown = set(data) - {"menu_caption"}
    if unknown:
        raise ValueError(f"Unknown DGpy configuration keys: {sorted(unknown)}")
    caption = data.get("menu_caption", "DGpy")
    if not isinstance(caption, str) or not caption.strip():
        raise ValueError("menu_caption must be a non-empty string")
    return Config(menu_caption=caption)
