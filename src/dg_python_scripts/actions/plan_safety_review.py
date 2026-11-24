"""Read-only, host-independent structural audits of existing Action plans.

These functions do NOT establish Flame object capabilities, marker freshness,
permission, user confirmation, name namespace, or safe rollback. They do not
call apply_plan(), apply_delete_plan(), flame, Qt or any object property.
A passing audit is NEVER permission to execute, rename or delete anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dg_python_scripts.markers import MarkerDeletePlan, MarkerDeleteTarget
from dg_python_scripts.rename import RenamePlan, RenamePreviewRow, RenameTarget

_MAX_PLAN_TARGETS = 256


@dataclass(frozen=True)
class ActionPlanReview:
    """Sanitized diagnostic summary; contains no host refs or private names."""

    findings: tuple[str, ...]
    operation: str
    target_count: int = 0
    change_count: int = 0
    requires_live_recheck: bool = True
    requires_operator_confirmation: bool = False

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"

    @property
    def next_step(self) -> str:
        return "MANUAL_RECONCILIATION" if self.findings else "NO_CHANGE"


def _blocked(code: str, operation: str, *, confirmation: bool = False) -> ActionPlanReview:
    return ActionPlanReview((code,), operation, requires_operator_confirmation=confirmation)


def _plain_name(value: Any) -> bool:
    # Validate just the proposed *new* value; no assumptions about the
    # host's naming namespace, collisions, Unicode or permissions.
    return (type(value) is str and bool(value.strip()) and
            not any(ord(char) < 32 or ord(char) == 127 for char in value))


def review_rename_plan(plan: object) -> ActionPlanReview:
    """Detect structural contradictions/aliases in a *captured* RenamePlan.

    Real name.get_value()/set_value() capability, the current name at click
    time, namespace conflicts and rollback behavior remain UNVERIFIED.
    """
    operation = "rename"
    if type(plan) is not RenamePlan:
        return _blocked("invalid_rename_plan", operation)
    if type(plan.rows) is not tuple or not 1 <= len(plan.rows) <= _MAX_PLAN_TARGETS:
        return _blocked("invalid_rename_rows", operation)

    seen_targets: set[int] = set()
    seen_attributes: set[int] = set()
    proposed_names: set[str] = set()
    changes = 0
    valid_targets = 0
    for row in plan.rows:
        if type(row) is not RenamePreviewRow:
            return _blocked("invalid_rename_row", operation)
        if type(row.status) is not str or row.status not in {
            "ready", "unchanged", "unsupported"
        }:
            return _blocked("unknown_rename_row_status", operation)
        if row.status == "unsupported":
            if row.target is not None or row.new_name is not None:
                return _blocked("contradictory_unsupported_row", operation)
            continue
        if type(row.target) is not RenameTarget:
            return _blocked("missing_rename_target", operation)
        target = row.target
        if (type(row.original_name) is not str or
                type(target.original_name) is not str or
                row.original_name != target.original_name):
            return _blocked("rename_original_mismatch", operation)
        if not _plain_name(row.new_name):
            return _blocked("invalid_proposed_name", operation)
        if (row.status == "ready") != (row.new_name != row.original_name):
            return _blocked("rename_row_status_mismatch", operation)
        target_id = id(target.obj)
        name_attribute_id = id(target.name_attribute)
        if target_id in seen_targets:
            return _blocked("duplicate_rename_target", operation)
        if name_attribute_id in seen_attributes:
            return _blocked("aliased_rename_attribute", operation)
        seen_targets.add(target_id)
        seen_attributes.add(name_attribute_id)
        valid_targets += 1
        if row.status == "ready":
            # Duplicate proposed names may be valid in different reels,
            # but without independent namespace evidence we must STOP.
            if row.new_name in proposed_names:
                return _blocked("unverified_rename_name_collision", operation)
            proposed_names.add(row.new_name)
            changes += 1
    if changes == 0:
        return _blocked("no_rename_changes", operation)
    return ActionPlanReview((), operation, valid_targets, changes)


def review_marker_delete_plan(plan: object) -> ActionPlanReview:
    """Check a captured MarkerDeletePlan WITHOUT re-reading host markers.

    This cannot certify that captured markers are still present or that an
    actual delete() is safe. The caller must NOT use this to skip a fresh
    host-side comparison or the existing operator confirmation dialog.
    """
    operation = "delete_markers"
    if type(plan) is not MarkerDeletePlan:
        return _blocked("invalid_marker_plan", operation, confirmation=True)
    if type(plan.targets) is not tuple or not 1 <= len(plan.targets) <= _MAX_PLAN_TARGETS:
        return _blocked("invalid_marker_targets", operation, confirmation=True)
    seen_targets: set[int] = set()
    seen_markers: set[int] = set()
    markers_to_delete = 0
    for target in plan.targets:
        if type(target) is not MarkerDeleteTarget:
            return _blocked("invalid_marker_target", operation, confirmation=True)
        if type(target.type_name) is not str or target.type_name not in {
            "PyClip", "PySequence"
        }:
            return _blocked("unverified_marker_target_type", operation, confirmation=True)
        if type(target.markers) is not tuple:
            return _blocked("invalid_captured_markers", operation, confirmation=True)
        target_id = id(target.obj)
        if target_id in seen_targets:
            return _blocked("duplicate_marker_target", operation, confirmation=True)
        seen_targets.add(target_id)
        for marker in target.markers:
            if marker is None or type(marker) in (str, int, float, bool, bytes):
                return _blocked("invalid_marker_reference", operation, confirmation=True)
            marker_id = id(marker)
            if marker_id in seen_markers:
                return _blocked("duplicate_marker_reference", operation, confirmation=True)
            seen_markers.add(marker_id)
            markers_to_delete += 1
    if markers_to_delete == 0:
        return _blocked("no_captured_markers", operation, confirmation=True)
    return ActionPlanReview((), operation, len(seen_targets), markers_to_delete,
                            requires_live_recheck=True,
                            requires_operator_confirmation=True)
