"""Discover direct clip/sequence marker targets and delete their markers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

_TARGET_CLASS_NAMES = frozenset({"PyClip", "PySequence"})
_PARENT_CLASS_NAMES = frozenset({"PyReel"})


class MarkerDeleteError(RuntimeError):
    """Base error for marker discovery or deletion failures."""


class MarkerApplyError(MarkerDeleteError):
    """Deletion stopped; deleted is a best-effort net estimate, not a verified count."""

    def __init__(self, message: str, *, deleted: int = 0):
        self.deleted = deleted
        super().__init__(message)


class StaleMarkerDeleteError(MarkerApplyError):
    """Preview snapshot no longer matches; no delete callback was invoked."""


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


def _same_marker_snapshot(actual: tuple[Any, ...], expected: tuple[Any, ...]) -> bool:
    """Conservative proxy-identity comparison, NOT verified Flame marker UID."""
    return len(actual) == len(expected) and all(
        a is b for a, b in zip(actual, expected)
    )


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

    # Recheck *all* captured collections before the very first destructive
    # callback. Compare identity, not proxy equality: a new or reordered
    # proxy is conservatively treated as stale until Flame validates it.
    # This is NOT atomic with deletion and cannot eliminate host races.
    for target in plan.targets:
        try:
            current = _as_tuple(
                getattr(target.obj, "markers"),
                label=f"markers of {target.display_name!r}",
            )
        except Exception as error:
            raise StaleMarkerDeleteError(
                f"Could not revalidate markers for {target.display_name!r} "
                "before deletion; DGpy made no delete calls.",
                deleted=0,
            ) from error
        if not _same_marker_snapshot(current, target.markers):
            raise StaleMarkerDeleteError(
                f"Markers changed since preview for {target.display_name!r}; "
                "DGpy made no delete calls.",
                deleted=0,
            )

    deleted = 0
    changed_targets = 0

    for target in plan.targets:
        if not target.markers:
            continue

        # A prior target's callback may have changed this target *after*
        # the all-target preflight. Stop before touching its stale refs.
        # This recheck still cannot prevent a host change immediately
        # after it or guarantee stable Python proxy identities.
        try:
            current = _as_tuple(
                getattr(target.obj, "markers"),
                label=f"markers of {target.display_name!r}",
            )
        except Exception as error:
            raise MarkerApplyError(
                f"Could not revalidate markers for {target.display_name!r} "
                "during deletion; no further delete calls were made.",
                deleted=deleted,
            ) from error
        if not _same_marker_snapshot(current, target.markers):
            raise MarkerApplyError(
                f"Markers changed for {target.display_name!r} during deletion; "
                "no further delete calls were made.",
                deleted=deleted,
            )

        for marker_index, marker in enumerate(target.markers):
            if marker_index:
                # The preceding callback could silently remove, replace,
                # reorder, or insert *other* markers on this same target.
                # Compare the exact expected remainder before issuing the
                # next delete. This is still not atomic with host mutations.
                try:
                    current = _as_tuple(
                        getattr(target.obj, "markers"),
                        label=f"markers of {target.display_name!r}",
                    )
                except Exception as error:
                    raise MarkerApplyError(
                        f"Could not revalidate remaining markers for "
                        f"{target.display_name!r} during deletion; "
                        "no further delete calls were made.",
                        deleted=deleted,
                    ) from error
                expected = target.markers[marker_index:]
                if not _same_marker_snapshot(current, expected):
                    # A net count can underestimate or overestimate the
                    # actual successful delete operations after a race.
                    estimate = max(0, target.marker_count - len(current))
                    raise MarkerApplyError(
                        f"Marker deletion was incomplete for "
                        f"{target.display_name!r}: "
                        f"{len(current)} marker(s) remain or changed "
                        "during deletion; no further delete calls were made.",
                        deleted=deleted + estimate,
                    )

            try:
                delete_marker(marker)
            except Exception as error:
                # A callback may mutate its target *and then* raise.
                # Count is an estimate from the live length difference,
                # not a trustworthy number of successful delete calls.
                try:
                    remaining = _as_tuple(
                        getattr(target.obj, "markers"),
                        label=f"markers of {target.display_name!r}",
                    )
                except Exception:
                    raise MarkerApplyError(
                        f"Delete callback failed for {target.display_name!r} "
                        f"({type(error).__name__}: {error}); read-back unavailable. "
                        "No further delete calls were made.",
                        deleted=deleted,
                    ) from error
                estimate = max(0, target.marker_count - len(remaining))
                raise MarkerApplyError(
                    f"Delete callback failed for {target.display_name!r} "
                    f"({type(error).__name__}: {error}); "
                    "no further delete calls were made.",
                    deleted=deleted + estimate,
                ) from error

        try:
            remaining = _as_tuple(
                getattr(target.obj, "markers"),
                label=f"markers of {target.display_name!r}",
            )
        except Exception as error:
            raise MarkerApplyError(
                f"Could not verify deletion for {target.display_name!r} "
                f"({type(error).__name__}: {error}); "
                "no further delete calls were made.",
                deleted=deleted,
            ) from error

        removed = max(0, target.marker_count - len(remaining))
        deleted += removed
        if removed:
            changed_targets += 1

        if remaining:
            raise MarkerApplyError(
                f"Marker deletion was incomplete:\n- {target.display_name}: "
                f"{len(remaining)} marker(s) remain; "
                "no further delete calls were made.",
                deleted=deleted,
            )

    return MarkerDeleteResult(deleted=deleted, changed_targets=changed_targets)
