"""Capability-based batch rename planning and best-effort apply/rollback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from string import Formatter
import re
import time
from typing import Any, Iterable

_UNSUPPORTED_CLASS_NAMES = frozenset({"PyBatchIteration"})
_INDEX_SPEC = re.compile(
    r"^(?P<padding>#+)?(?:@(?P<start>[+-]?\d+)(?P<step>[+-]\d+)?)?$"
)


class RenameError(RuntimeError):
    pass


class TemplateError(ValueError):
    pass


class StaleRenameError(RenameError):
    pass


class RenameApplyError(RenameError):
    def __init__(self, message: str, rollback_errors: Iterable[str] = ()):
        self.rollback_errors = tuple(rollback_errors)
        if self.rollback_errors:
            message = message + "\nRollback issues:\n- " + "\n- ".join(
                self.rollback_errors
            )
        super().__init__(message)


@dataclass(frozen=True)
class ReplacementRule:
    find: str
    replace: str

    def apply(self, value: str) -> str:
        if not self.find:
            return value
        return value.replace(self.find, self.replace)


@dataclass(frozen=True)
class RenameTarget:
    obj: Any
    name_attribute: Any
    type_name: str
    original_name: str


@dataclass(frozen=True)
class RenamePreviewRow:
    type_name: str
    original_name: str | None
    new_name: str | None
    status: str
    reason: str | None = None
    target: RenameTarget | None = None


@dataclass(frozen=True)
class RenamePlan:
    rows: tuple[RenamePreviewRow, ...]
    template: str
    replacements: tuple[ReplacementRule, ...]
    frozen_now: datetime
    # Retained for compatibility with the original single-rule API.
    find: str = ""
    replace: str = ""

    @property
    def ready_rows(self) -> tuple[RenamePreviewRow, ...]:
        return tuple(row for row in self.rows if row.status == "ready")


@dataclass(frozen=True)
class RenameApplyResult:
    changed: int


def _type_name(value: Any) -> str:
    cls = type(value)
    module = getattr(cls, "__module__", "")
    name = getattr(cls, "__qualname__", getattr(cls, "__name__", str(cls)))
    return f"{module}.{name}" if module else name


def probe_target(obj: Any) -> tuple[RenameTarget | None, str | None]:
    if type(obj).__name__ in _UNSUPPORTED_CLASS_NAMES:
        return None, "Flame manages this object's naming semantics"

    try:
        name_attribute = getattr(obj, "name")
    except Exception as error:
        return None, f"name unavailable: {type(error).__name__}"

    getter = getattr(name_attribute, "get_value", None)
    setter = getattr(name_attribute, "set_value", None)
    if not callable(getter) or not callable(setter):
        return None, "name is not writable through get_value()/set_value()"

    try:
        original_name = getter()
    except Exception as error:
        return None, f"could not read name: {type(error).__name__}: {error}"

    if not isinstance(original_name, str):
        return None, "name is not a string"

    return (
        RenameTarget(
            obj=obj,
            name_attribute=name_attribute,
            type_name=_type_name(obj),
            original_name=original_name,
        ),
        None,
    )


def can_rename_selection(selection: Iterable[Any]) -> bool:
    return any(probe_target(obj)[0] is not None for obj in selection)


def _format_index(spec: str, position: int) -> str:
    match = _INDEX_SPEC.fullmatch(spec)
    if match is None:
        raise TemplateError(
            "Invalid index format. Use {index}, {index:###}, "
            "{index:###@8}, or {index:###@8-2}."
        )

    padding = match.group("padding") or ""
    start = int(match.group("start")) if match.group("start") else 1
    step = int(match.group("step")) if match.group("step") else 1
    value = start + (position * step)
    return str(value).zfill(len(padding)) if padding else str(value)


def render_template(
    template: str,
    original_name: str,
    position: int,
    now: datetime,
) -> str:
    output: list[str] = []
    formatter = Formatter()

    try:
        parts = tuple(formatter.parse(template))
    except ValueError as error:
        raise TemplateError(str(error)) from error

    for literal, field_name, format_spec, conversion in parts:
        output.append(literal)
        if field_name is None:
            continue
        if conversion is not None:
            raise TemplateError("Token conversions are not supported")

        if field_name == "name":
            if format_spec:
                raise TemplateError("{name} does not accept a format")
            value = original_name
        elif field_name == "date":
            value = now.strftime(format_spec or "%Y%m%d")
        elif field_name == "index":
            value = _format_index(format_spec or "", position)
        else:
            raise TemplateError(f"Unknown token: {{{field_name}}}")

        output.append(value)

    return "".join(output)


def _replacement_rules(
    replacements: Iterable[ReplacementRule],
    legacy_find: str,
    legacy_replace: str,
) -> tuple[ReplacementRule, ...]:
    rules = tuple(replacements)
    if any(not isinstance(rule, ReplacementRule) for rule in rules):
        raise TypeError("replacements must contain ReplacementRule values")
    if legacy_find:
        return (ReplacementRule(legacy_find, legacy_replace),) + rules
    return rules


def build_plan(
    selection: Iterable[Any],
    template: str,
    find: str = "",
    replace: str = "",
    now: datetime | None = None,
    *,
    replacements: Iterable[ReplacementRule] = (),
) -> RenamePlan:
    frozen_now = now or datetime.now().astimezone()
    rows: list[RenamePreviewRow] = []
    rename_position = 0
    rules = _replacement_rules(replacements, find, replace)

    # Validate syntax even when every selected object is unsupported.
    render_template(template, "", 0, frozen_now)

    for obj in selection:
        target, reason = probe_target(obj)
        if target is None:
            rows.append(
                RenamePreviewRow(
                    type_name=_type_name(obj),
                    original_name=None,
                    new_name=None,
                    status="unsupported",
                    reason=reason,
                )
            )
            continue

        new_name = render_template(
            template,
            target.original_name,
            rename_position,
            frozen_now,
        )
        rename_position += 1

        # Replacement rules intentionally compose from top to bottom.
        for rule in rules:
            new_name = rule.apply(new_name)

        status = "unchanged" if new_name == target.original_name else "ready"
        rows.append(
            RenamePreviewRow(
                type_name=target.type_name,
                original_name=target.original_name,
                new_name=new_name,
                status=status,
                target=target,
            )
        )

    return RenamePlan(
        rows=tuple(rows),
        template=template,
        replacements=rules,
        frozen_now=frozen_now,
        find=find,
        replace=replace,
    )


def _read_name(target: RenameTarget) -> str:
    try:
        value = target.name_attribute.get_value()
    except Exception as error:
        raise RenameApplyError(
            f"Could not read {target.type_name} name: "
            f"{type(error).__name__}: {error}"
        ) from error
    if not isinstance(value, str):
        raise RenameApplyError(f"{target.type_name} name is no longer a string")
    return value


class _RenameStateDrift(RenameApplyError):
    """A guard found unexpected or unreadable state; do not write again."""


def _require_expected_name(target: RenameTarget, expected: str, stage: str) -> None:
    """Compare captured attribute state, not an atomic host-side guard."""
    guidance = "No further rename or rollback calls were made after this check."
    try:
        actual = _read_name(target)
    except RenameError as error:
        raise _RenameStateDrift(
            f"Could not verify name during {stage} for {target.type_name} "
            f"(original {target.original_name!r}): {error}. {guidance}"
        ) from error
    if actual != expected:
        raise _RenameStateDrift(
            f"Unexpected name during {stage} for {target.type_name} "
            f"(original {target.original_name!r}): "
            f"expected {expected!r}, actual {actual!r}. {guidance}"
        )


def _write_exact(target: RenameTarget, requested: str) -> None:
    try:
        target.name_attribute.set_value(requested)
    except Exception as error:
        raise RenameApplyError(
            f"Could not rename {target.type_name} "
            f"{target.original_name!r} to {requested!r}: "
            f"{type(error).__name__}: {error}"
        ) from error

    actual = _read_name(target)
    if actual != requested:
        raise RenameApplyError(
            f"Flame did not apply the requested name for {target.type_name}: "
            f"requested {requested!r}, actual {actual!r}"
        )


def _verify_original_names(rows: tuple[RenamePreviewRow, ...]) -> tuple[str, ...]:
    """Read-only final rollback check; does not imply an atomic snapshot."""
    errors: list[str] = []
    for row in rows:
        target = row.target
        assert target is not None
        try:
            actual = _read_name(target)
        except RenameError as error:
            errors.append(
                f"Could not verify original name {target.original_name!r}: {error}"
            )
            continue
        if actual != target.original_name:
            errors.append(
                f"Original name not restored for {target.type_name}: "
                f"expected {target.original_name!r}, actual {actual!r}"
            )
    return tuple(errors)


def _rollback_after_final_failure(
    rows: tuple[RenamePreviewRow, ...],
    nonce: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    moved: set[int] = set()

    for index, row in enumerate(rows):
        target = row.target
        assert target is not None
        temporary = f"__DGPY_ROLLBACK_{nonce}_{index:04d}__"
        try:
            _write_exact(target, temporary)
        except RenameError as error:
            errors.append(str(error))
        else:
            moved.add(index)

    for index, row in enumerate(rows):
        target = row.target
        assert target is not None
        if index not in moved:
            try:
                if _read_name(target) == target.original_name:
                    continue
            except RenameError as error:
                errors.append(str(error))
                continue
        try:
            _write_exact(target, target.original_name)
        except RenameError as error:
            errors.append(str(error))

    return tuple(errors)


def apply_plan(plan: RenamePlan) -> RenameApplyResult:
    rows = plan.ready_rows
    if not rows:
        return RenameApplyResult(changed=0)

    for row in rows:
        target = row.target
        assert target is not None
        current = _read_name(target)
        if current != target.original_name:
            raise StaleRenameError(
                f"{target.type_name} changed since preview: "
                f"expected {target.original_name!r}, found {current!r}"
            )

    nonce = f"{time.time_ns():x}"
    # A setter can mutate a name and *then* raise, or its read-back can
    # fail after a successful write. Record each attempted target *before*
    # writing so the failing target is also considered for rollback.
    attempted_rows: list[RenamePreviewRow] = []

    try:
        for index, row in enumerate(rows):
            target = row.target
            assert target is not None
            _require_expected_name(
                target, target.original_name, "temporary rename pre-write"
            )
            attempted_rows.append(row)
            _write_exact(target, f"__DGPY_TMP_{nonce}_{index:04d}__")
    except _RenameStateDrift:
        # Unexpected or unreadable state can be another host/user edit.
        # Do not attempt to repair or overwrite it. Earlier writes may
        # remain; the existing UI handles this as an uncertain failure.
        raise
    except RenameError as error:
        rollback_errors: list[str] = []
        for row in reversed(attempted_rows):
            target = row.target
            assert target is not None
            try:
                # Avoid an unnecessary setter call when the failed write
                # left the original name unchanged.
                if _read_name(target) == target.original_name:
                    continue
            except RenameError:
                # Unknown state: best-effort restoration with verified
                # read-back, not a claim of transactional host semantics.
                pass
            try:
                _write_exact(target, target.original_name)
            except RenameError as rollback_error:
                rollback_errors.append(str(rollback_error))
        # A later rollback setter can change an earlier row, and a failed
        # callback can affect a row we never attempted. Inspect every ready
        # row without writing to it or trying another round of recovery.
        rollback_errors.extend(_verify_original_names(rows))
        raise RenameApplyError(str(error), rollback_errors) from error

    try:
        for index, row in enumerate(rows):
            target = row.target
            assert target is not None
            assert row.new_name is not None
            _require_expected_name(
                target, f"__DGPY_TMP_{nonce}_{index:04d}__", "final rename pre-write"
            )
            _write_exact(target, row.new_name)
    except _RenameStateDrift:
        # The existing compensation path is for setter/read-back
        # failures, not a newly detected conflicting or unknown state.
        raise
    except RenameError as error:
        rollback_errors = _rollback_after_final_failure(rows, nonce)
        rollback_errors += _verify_original_names(rows)
        raise RenameApplyError(str(error), rollback_errors) from error

    # A later setter can invalidate an earlier successful read-back.
    # Inspect all ready rows before returning success; a mismatch or
    # unknown value stops without further writes or automatic recovery.
    for row in rows:
        target = row.target
        assert target is not None
        assert row.new_name is not None
        _require_expected_name(target, row.new_name, "final verification")

    return RenameApplyResult(changed=len(rows))
