"""Discover direct clip/sequence marker targets and delete their markers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

_TARGET_CLASS_NAMES = frozenset({"PyClip", "PySequence"})
_PARENT_CLASS_NAMES = frozenset({"PyReel", "PyFolder", "PyLibrary"})


class MarkerDeleteError(RuntimeError):
    """Base error for marker discovery or deletion failures."""


class MarkerApplyError(MarkerDeleteError):
    def __init__(self, message: str, *, deleted: int = 0):
        self.deleted = deleted
        super().__init__(message)


@dataclass(frozen=True)
class MarkerDeleteTarget:
    obj: Any
    type_name: str
    display_name: str
    markers: tuple[Any, ...]

    @property
    def marker_count(self) -> int:
        return len(self.markers)


@dataclass(frozen=True)
class MarkerDeletePlan:
    targets: tuple[MarkerDeleteTarget, ...]

    @property
    def total_markers(self) -> int:
        return sum(target.marker_count for target in self.targets)

    @property
    def marked_targets(self) -> tuple[MarkerDeleteTarget, ...]:
        return tuple(target for target in self.targets if target.marker_count)


@dataclass(frozen=True)
class MarkerDeleteResult:
    deleted: int
    changed_targets: int


def _class_name(obj: Any) -> str:
    return type(obj).__name__


def _display_name(obj: Any) -> str:
    try:
        value = getattr(obj, "name")
    except Exception:
        return _class_name(obj)

    getter = getattr(value, "get_value", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            return _class_name(obj)

    return value if isinstance(value, str) and value else _class_name(obj)


def _as_tuple(value: Any, *, label: str) -> tuple[Any, ...]:
    try:
        return tuple(value)
    except Exception as error:
        raise MarkerDeleteError(
            f"Could not read {label}: {type(error).__name__}: {error}"
        ) from error


def can_delete_markers_selection(selection: Iterable[Any]) -> bool:
    try:
        items = tuple(selection)
    except Exception:
        return False

    supported = _TARGET_CLASS_NAMES | _PARENT_CLASS_NAMES
    return any(_class_name(obj) in supported for obj in items)


def collect_marker_targets(selection: Iterable[Any]) -> tuple[Any, ...]:
    """Return selected targets plus direct clips/sequences from selected parents."""

    selected = _as_tuple(selection, label="selection")
    targets: list[Any] = []
    seen: set[int] = set()

    def add(obj: Any) -> None:
        key = id(obj)
        if key in seen:
            return
        seen.add(key)
        targets.append(obj)

    for obj in selected:
        class_name = _class_name(obj)
        if class_name in _TARGET_CLASS_NAMES:
            add(obj)
            continue

        if class_name not in _PARENT_CLASS_NAMES:
            continue

        for attribute_name in ("clips", "sequences"):
            try:
                children = getattr(obj, attribute_name)
            except Exception as error:
                raise MarkerDeleteError(
                    f"Could not read {attribute_name} from {_display_name(obj)!r}: "
                    f"{type(error).__name__}: {error}"
                ) from error

            for child in _as_tuple(
                children,
                label=f"{attribute_name} of {_display_name(obj)!r}",
            ):
                if _class_name(child) in _TARGET_CLASS_NAMES:
                    add(child)

    return tuple(targets)


def build_delete_plan(selection: Iterable[Any]) -> MarkerDeletePlan:
    rows: list[MarkerDeleteTarget] = []
    for obj in collect_marker_targets(selection):
        try:
            markers = getattr(obj, "markers")
        except Exception as error:
            raise MarkerDeleteError(
                f"Could not read markers from {_display_name(obj)!r}: "
                f"{type(error).__name__}: {error}"
            ) from error

        rows.append(
            MarkerDeleteTarget(
                obj=obj,
                type_name=_class_name(obj),
                display_name=_display_name(obj),
                markers=_as_tuple(markers, label=f"markers of {_display_name(obj)!r}"),
            )
        )

    return MarkerDeletePlan(tuple(rows))


def apply_delete_plan(
    plan: MarkerDeletePlan,
    delete_marker: Callable[[Any], Any],
) -> MarkerDeleteResult:
    """Delete captured markers one at a time and verify exact read-back."""

    if not callable(delete_marker):
        raise TypeError("delete_marker must be callable")

    deleted = 0
    changed_targets = 0
    failures: list[str] = []

    for target in plan.targets:
        if not target.markers:
            continue

        delete_errors: list[str] = []
        for marker in target.markers:
            try:
                delete_marker(marker)
            except Exception as error:
                delete_errors.append(f"{type(error).__name__}: {error}")

        try:
            remaining = _as_tuple(
                getattr(target.obj, "markers"),
                label=f"markers of {target.display_name!r}",
            )
        except Exception as error:
            failures.append(
                f"{target.display_name}: could not verify deletion "
                f"({type(error).__name__}: {error})"
            )
            continue

        removed = max(0, target.marker_count - len(remaining))
        deleted += removed
        if removed:
            changed_targets += 1

        if remaining:
            detail = (
                f"; delete errors: {' | '.join(delete_errors)}"
                if delete_errors
                else ""
            )
            failures.append(
                f"{target.display_name}: {len(remaining)} marker(s) remain{detail}"
            )

    if failures:
        raise MarkerApplyError(
            "Marker deletion was incomplete:\n- " + "\n- ".join(failures),
            deleted=deleted,
        )

    return MarkerDeleteResult(deleted=deleted, changed_targets=changed_targets)
