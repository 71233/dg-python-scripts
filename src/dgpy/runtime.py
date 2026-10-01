"""Lazy Flame runtime detection, isolated from package initialization."""

from dataclasses import dataclass
import importlib
import platform
import re

PRIMARY_VERSION = (2025, 2, 7)


@dataclass(frozen=True)
class RuntimeInfo:
    flame_version: str | None
    version: tuple[int, int, int] | None
    python_version: str

    @property
    def status(self) -> str:
        if self.flame_version is None:
            return "outside-flame"
        if self.version == PRIMARY_VERSION:
            return "primary"
        return "unvalidated"


def parse_version(value: str) -> tuple[int, int, int] | None:
    """Accept a release version with an optional product prefix/build suffix."""
    match = re.search(r"(?<!\d)(20\d{2})\.(\d+)(?:\.(\d+))?(?!\d)", value)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def detect_runtime() -> RuntimeInfo:
    try:
        flame = importlib.import_module("flame")
    except ModuleNotFoundError as error:
        if error.name != "flame":
            raise
        return RuntimeInfo(None, None, platform.python_version())
    value = str(flame.get_version())
    return RuntimeInfo(value, parse_version(value), platform.python_version())
