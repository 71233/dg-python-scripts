"""Read-only structural audits of existing DGpy plan snapshot fixtures.

Tests in a disposable container. No simulated operation mutates a marker,
changes a clip name, or invokes any Flame API.
"""

from dataclasses import replace
from datetime import datetime, timezone
import builtins
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from dg_python_scripts.actions.plan_safety_review import (
    ActionPlanReview,
    review_rename_plan,
    review_marker_delete_plan,
)
from dg_python_scripts.markers import MarkerDeletePlan, MarkerDeleteTarget
from dg_python_scripts.rename import RenamePlan, RenamePreviewRow, RenameTarget

STAMP = datetime(2026, 11, 23, tzinfo=timezone.utc)


class DangerousProxy:
    def __getattribute__(self, name):
        raise AssertionError("must not inspect target object: " + name)

    def __bool__(self):
        raise AssertionError("must not coerce target object")

    def __eq__(self, other):
        raise AssertionError("must not compare target objects")

    def __repr__(self):
        raise AssertionError("must not log target object")


class PyMarker(DangerousProxy):
    pass


class PyClip(DangerousProxy):
    pass


def rename_row(obj=None, attr=None, original="Original", new="New", status="ready"):
    obj = DangerousProxy() if obj is None else obj
    attr = DangerousProxy() if attr is None else attr
    target = RenameTarget(obj, attr, "PyClip", original)
    return RenamePreviewRow("PyClip", original, new, status, target=target)


def rename_plan(rows=None):
    if rows is None:
        rows = (rename_row(),)
    return RenamePlan(tuple(rows), "{name}", (), STAMP)


def marker_target(obj=None, markers=None, type_name="PyClip"):
    if obj is None:
        obj = PyClip()
    if markers is None:
        markers = (PyMarker(),)
    return MarkerDeleteTarget(obj, type_name, "private clip name", markers)


def marker_plan(targets=None):
    return MarkerDeletePlan(tuple(targets) if targets is not None else (marker_target(),))


class PlanSafetyReviewTests(unittest.TestCase):
    def blocked(self, report, code):
        self.assertEqual(report.findings, (code,), report)
        self.assertEqual(report.status, "BLOCKED")
        self.assertEqual(report.next_step, "MANUAL_RECONCILIATION")
        self.assertTrue(report.requires_live_recheck)
        self.assertEqual(report.target_count, 0)
        self.assertEqual(report.change_count, 0)
        return report

    def test_rename_valid_snapshot_still_no_change(self):
        result = review_rename_plan(rename_plan())
        self.assertEqual((result.status, result.operation, result.target_count,
                          result.change_count, result.next_step),
                         ("PREVIEW_ONLY", "rename", 1, 1, "NO_CHANGE"))
        self.assertTrue(result.requires_live_recheck)
        self.assertFalse(result.requires_operator_confirmation)
        for name in ("apply", "execute", "rename", "delete", "restore"):
            self.assertFalse(hasattr(result, name))

    def test_marker_valid_snapshot_needs_recheck_and_confirmation(self):
        result = review_marker_delete_plan(marker_plan())
        self.assertEqual((result.status, result.operation, result.target_count,
                          result.change_count, result.next_step),
                         ("PREVIEW_ONLY", "delete_markers", 1, 1, "NO_CHANGE"))
        self.assertTrue(result.requires_live_recheck)
        self.assertTrue(result.requires_operator_confirmation)
        self.assertFalse(hasattr(result, "apply"))

    def test_rename_invalid_plan_type(self):
        self.blocked(review_rename_plan(None), "invalid_rename_plan")
        self.blocked(review_rename_plan({}), "invalid_rename_plan")

    def test_rename_invalid_rows(self):
        self.blocked(review_rename_plan(rename_plan(())), "invalid_rename_rows")
        self.blocked(review_rename_plan(replace(rename_plan(), rows=[rename_row()])),
                     "invalid_rename_rows")
        self.blocked(review_rename_plan(rename_plan(tuple(rename_row() for _ in range(257)))),
                     "invalid_rename_rows")

    def test_rename_invalid_row(self):
        self.blocked(review_rename_plan(rename_plan((object(),))), "invalid_rename_row")

    def test_rename_unknown_row_status(self):
        row = replace(rename_row(), status="maybe")
        self.blocked(review_rename_plan(rename_plan((row,))),
                     "unknown_rename_row_status")

    def test_rename_unsupported_is_not_actionable(self):
        row = RenamePreviewRow("PyNode", None, None, "unsupported", "no name", None)
        self.blocked(review_rename_plan(rename_plan((row,))), "no_rename_changes")

    def test_rename_unsupported_cannot_hold_target(self):
        row = replace(rename_row(), status="unsupported")
        self.blocked(review_rename_plan(rename_plan((row,))),
                     "contradictory_unsupported_row")

    def test_rename_missing_target(self):
        row = replace(rename_row(), target=None)
        self.blocked(review_rename_plan(rename_plan((row,))), "missing_rename_target")

    def test_rename_original_drift(self):
        row = replace(rename_row(), original_name="Someone else")
        self.blocked(review_rename_plan(rename_plan((row,))), "rename_original_mismatch")

    def test_rename_blank_and_control_names(self):
        for name in ("", "  ", "\x00bad", "new\nline", "a\x7fb"):
            with self.subTest(name=repr(name)):
                row = replace(rename_row(), new_name=name)
                self.blocked(review_rename_plan(rename_plan((row,))),
                             "invalid_proposed_name")

    def test_rename_status_inconsistent_with_name(self):
        row = replace(rename_row(), status="unchanged")
        self.blocked(review_rename_plan(rename_plan((row,))),
                     "rename_row_status_mismatch")
        row = replace(rename_row(), new_name="Original", status="ready")
        self.blocked(review_rename_plan(rename_plan((row,))),
                     "rename_row_status_mismatch")

    def test_rename_duplicate_object_caught_without_eq(self):
        obj = DangerousProxy()
        rows = (rename_row(obj=obj, new="A"), rename_row(obj=obj, new="B"))
        self.blocked(review_rename_plan(rename_plan(rows)), "duplicate_rename_target")

    def test_rename_name_attribute_alias_caught(self):
        attr = DangerousProxy()
        rows = (rename_row(attr=attr, new="A"), rename_row(attr=attr, new="B"))
        self.blocked(review_rename_plan(rename_plan(rows)), "aliased_rename_attribute")

    def test_rename_proposed_collision_blocked_without_host_namespace(self):
        rows = (rename_row(new="Same"), rename_row(new="Same"))
        self.blocked(review_rename_plan(rename_plan(rows)),
                     "unverified_rename_name_collision")

    def test_rename_ready_and_unchanged_rows(self):
        unchanged = rename_row(new="Original", status="unchanged")
        report = review_rename_plan(rename_plan((rename_row(), unchanged)))
        self.assertEqual((report.status, report.target_count, report.change_count),
                         ("PREVIEW_ONLY", 2, 1))

    def test_rename_all_unchanged_blocked(self):
        row = rename_row(new="Original", status="unchanged")
        self.blocked(review_rename_plan(rename_plan((row,))), "no_rename_changes")

    def test_marker_invalid_plan_and_targets(self):
        self.blocked(review_marker_delete_plan(None), "invalid_marker_plan")
        self.blocked(review_marker_delete_plan(marker_plan(())), "invalid_marker_targets")
        self.blocked(review_marker_delete_plan(replace(marker_plan(), targets=[])),
                     "invalid_marker_targets")
        self.blocked(review_marker_delete_plan(marker_plan(tuple(marker_target()
                     for _ in range(257)))), "invalid_marker_targets")

    def test_marker_invalid_target_type(self):
        self.blocked(review_marker_delete_plan(marker_plan((object(),))),
                     "invalid_marker_target")
        self.blocked(review_marker_delete_plan(marker_plan((marker_target(type_name="PyReel"),))),
                     "unverified_marker_target_type")

    def test_marker_clip_and_sequence_names_are_only_claims(self):
        clip = marker_target()
        sequence = marker_target(type_name="PySequence")
        report = review_marker_delete_plan(marker_plan((clip, sequence)))
        self.assertEqual(report.status, "PREVIEW_ONLY")
        self.assertTrue(report.requires_operator_confirmation)
        self.assertTrue(report.requires_live_recheck)

    def test_marker_list_not_immutable_snapshot(self):
        target = replace(marker_target(), markers=[PyMarker()])
        self.blocked(review_marker_delete_plan(marker_plan((target,))),
                     "invalid_captured_markers")

    def test_marker_duplicate_target_identity(self):
        obj = PyClip()
        targets = (marker_target(obj=obj), marker_target(obj=obj))
        self.blocked(review_marker_delete_plan(marker_plan(targets)),
                     "duplicate_marker_target")

    def test_marker_duplicate_marker_identity_across_targets(self):
        marker = PyMarker()
        targets = (marker_target(markers=(marker,)), marker_target(markers=(marker,)))
        self.blocked(review_marker_delete_plan(marker_plan(targets)),
                     "duplicate_marker_reference")

    def test_marker_duplicate_within_target(self):
        marker = PyMarker()
        self.blocked(review_marker_delete_plan(marker_plan((marker_target(markers=(marker, marker)),))),
                     "duplicate_marker_reference")

    def test_marker_invalid_marker_reference(self):
        for bad in (None, "not-a-marker", 1, True, 3.14, b"raw"):
            with self.subTest(type=type(bad).__name__):
                self.blocked(review_marker_delete_plan(marker_plan((marker_target(markers=(bad,)),))),
                             "invalid_marker_reference")

    def test_marker_no_markers_to_delete(self):
        self.blocked(review_marker_delete_plan(marker_plan((marker_target(markers=()),))),
                     "no_captured_markers")

    def test_marker_mixed_empty_and_nonempty(self):
        result = review_marker_delete_plan(marker_plan((marker_target(markers=()), marker_target())))
        self.assertEqual((result.status, result.target_count, result.change_count),
                         ("PREVIEW_ONLY", 2, 1))

    def test_report_redacts_private_target_names_and_references(self):
        obj = DangerousProxy()
        name_attr = DangerousProxy()
        rename = review_rename_plan(rename_plan((rename_row(obj=obj, attr=name_attr),)))
        delete = review_marker_delete_plan(marker_plan((marker_target(obj=obj),)))
        for report in (rename, delete):
            text = repr(report)
            self.assertNotIn("private", text)
            self.assertNotIn("Original", text)
            self.assertNotIn("DangerousProxy", text)
            self.assertNotIn("object at", text)

    def test_no_file_io_or_host_import(self):
        with patch.object(builtins, "open", side_effect=AssertionError("disk I/O")), \
             patch.object(Path, "resolve", side_effect=AssertionError("disk I/O")):
            self.assertEqual(review_rename_plan(rename_plan()).status, "PREVIEW_ONLY")
            self.assertEqual(review_marker_delete_plan(marker_plan()).status, "PREVIEW_ONLY")
        self.assertNotIn("flame", sys.modules)
        self.assertNotIn("PySide6", sys.modules)


if __name__ == "__main__":
    unittest.main()
