"""Disposable failure-injection regression tests for existing Action applies.

These test doubles are never Flame objects. They demonstrate fail-closed
behavior without touching an actual Project, Clip, Hook, profile or disk.
"""

import sys
import types
import unittest
from unittest.mock import patch

from dg_python_scripts.rename import (
    RenameApplyError,
    StaleRenameError,
    apply_plan,
    build_plan,
)
from dg_python_scripts.markers import (
    MarkerApplyError,
    StaleMarkerDeleteError,
    apply_delete_plan,
    build_delete_plan,
)
from dg_python_scripts.actions.delete_markers_action import show_delete_markers


class FakeName:
    def __init__(self, value, *, failure=None):
        self.value = value
        self.original = value
        self.failure = failure
        self.calls = []

    def get_value(self):
        if self.failure == "temp_readback_once" and self.value.startswith("__DGPY_TMP_"):
            self.failure = None
            raise RuntimeError("injected temporary read-back failure")
        return self.value

    def set_value(self, new_value):
        self.calls.append(new_value)
        if self.failure == "temp_before_write" and new_value.startswith("__DGPY_TMP_"):
            self.failure = None
            raise RuntimeError("injected setter rejection")
        self.value = new_value
        if self.failure == "temp_after_write" and new_value.startswith("__DGPY_TMP_"):
            self.failure = None
            raise RuntimeError("injected partial temporary write failure")
        if self.failure == "restore_after_write" and new_value == self.original:
            self.failure = None
            raise RuntimeError("injected restore readback failure")
        if self.failure == "final_after_write" and new_value.startswith("New_"):
            self.failure = None
            raise RuntimeError("injected final write failure")


class PyClip:
    def __init__(self, name, markers=(), *, name_failure=None):
        self.name = FakeName(name, failure=name_failure)
        self.markers = list(markers)


class PyMarker:
    pass


class PySequence(PyClip):
    def __init__(self, name, markers=()):
        super().__init__(name, markers)
        self.deny_read = False

    def __getattribute__(self, key):
        if key == "markers" and object.__getattribute__(self, "deny_read"):
            raise RuntimeError("injected marker read failure")
        return object.__getattribute__(self, key)


def deletion_fixture():
    first_marker, second_marker = PyMarker(), PyMarker()
    first = PyClip("First", (first_marker,))
    second = PyClip("Second", (second_marker,))
    plan = build_delete_plan((first, second))
    return first, second, first_marker, second_marker, plan


def recording_delete(*clips):
    calls = []

    def callback(marker):
        calls.append(marker)
        for clip in clips:
            if any(item is marker for item in clip.markers):
                clip.markers[:] = [item for item in clip.markers if item is not marker]
                return
        raise RuntimeError("marker not found")

    return callback, calls


class RenameTemporaryFailureTests(unittest.TestCase):
    def test_second_target_setter_mutates_then_raises_and_both_restore(self):
        first = PyClip("First")
        second = PyClip("Second", name_failure="temp_after_write")
        plan = build_plan((first, second), "New_{index}")
        with self.assertRaises(RenameApplyError):
            apply_plan(plan)
        self.assertEqual(first.name.value, "First")
        self.assertEqual(second.name.value, "Second")
        self.assertTrue(any(x.startswith("__DGPY_TMP_") for x in second.name.calls))
        self.assertIn("Second", second.name.calls)

    def test_single_target_readback_failure_after_temp_write_restores(self):
        clip = PyClip("Original", name_failure="temp_readback_once")
        with self.assertRaises(RenameApplyError):
            apply_plan(build_plan((clip,), "New_{index}"))
        self.assertEqual(clip.name.value, "Original")
        self.assertTrue(any(x.startswith("__DGPY_TMP_") for x in clip.name.calls))

    def test_setter_rejects_before_mutation_does_not_rewrite_original(self):
        clip = PyClip("Original", name_failure="temp_before_write")
        with self.assertRaises(RenameApplyError):
            apply_plan(build_plan((clip,), "New_{index}"))
        self.assertEqual(clip.name.value, "Original")
        self.assertEqual(len(clip.name.calls), 1)

    def test_temp_failure_with_failed_restore_surfaces_rollback_issue(self):
        class IrrecoverableName(FakeName):
            def set_value(self, new_value):
                self.calls.append(new_value)
                if new_value.startswith("__DGPY_TMP_"):
                    self.value = new_value
                    raise RuntimeError("temporary write partially failed")
                if new_value == self.original:
                    raise RuntimeError("restore was rejected")
                self.value = new_value

        clip = PyClip("Original")
        clip.name = IrrecoverableName("Original")
        with self.assertRaises(RenameApplyError) as cm:
            apply_plan(build_plan((clip,), "New_{index}"))
        self.assertTrue(cm.exception.rollback_errors)
        self.assertTrue(clip.name.value.startswith("__DGPY_TMP_"))

    def test_stale_preview_before_any_write_remains_blocked(self):
        clip = PyClip("Original")
        plan = build_plan((clip,), "New_{index}")
        clip.name.value = "Changed outside DGpy"
        with self.assertRaises(StaleRenameError):
            apply_plan(plan)
        self.assertEqual(clip.name.calls, [])

    def test_no_failure_still_renames(self):
        first, second = PyClip("First"), PyClip("Second")
        result = apply_plan(build_plan((first, second), "New_{index}"))
        self.assertEqual(result.changed, 2)
        self.assertEqual((first.name.value, second.name.value), ("New_1", "New_2"))


class MarkerStalePreviewTests(unittest.TestCase):
    def assert_zero_deletions_on_stale(self, first, second, plan):
        delete, calls = recording_delete(first, second)
        before = (tuple(first.markers), tuple(second.markers))
        with self.assertRaises(StaleMarkerDeleteError) as cm:
            apply_delete_plan(plan, delete)
        self.assertIsInstance(cm.exception, MarkerApplyError)
        self.assertEqual(cm.exception.deleted, 0)
        self.assertEqual(calls, [])
        self.assertEqual((tuple(first.markers), tuple(second.markers)), before)

    def test_later_target_gained_marker_blocks_before_first_delete(self):
        first, second, _, _, plan = deletion_fixture()
        second.markers.append(PyMarker())
        self.assert_zero_deletions_on_stale(first, second, plan)

    def test_later_target_lost_marker_blocks_before_first_delete(self):
        first, second, _, _, plan = deletion_fixture()
        second.markers.clear()
        self.assert_zero_deletions_on_stale(first, second, plan)

    def test_same_count_replaced_marker_blocks(self):
        first, second, _, _, plan = deletion_fixture()
        second.markers[:] = [PyMarker()]
        self.assert_zero_deletions_on_stale(first, second, plan)

    def test_reordered_snapshot_blocks_without_comparing_proxy_equality(self):
        a, b = PyMarker(), PyMarker()
        clip = PyClip("Solo", (a, b))
        plan = build_delete_plan((clip,))
        clip.markers.reverse()
        delete, calls = recording_delete(clip)
        with self.assertRaises(StaleMarkerDeleteError) as cm:
            apply_delete_plan(plan, delete)
        self.assertEqual(cm.exception.deleted, 0)
        self.assertEqual(calls, [])

    def test_unreadable_later_target_blocks_without_deletion(self):
        first = PyClip("First", (PyMarker(),))
        second = PySequence("Second", (PyMarker(),))
        plan = build_delete_plan((first, second))
        self.assertEqual(len(plan.targets), 2)
        second.deny_read = True
        delete, calls = recording_delete(first, second)
        with self.assertRaises(StaleMarkerDeleteError) as cm:
            apply_delete_plan(plan, delete)
        self.assertEqual(cm.exception.deleted, 0)
        self.assertEqual(calls, [])
        self.assertEqual(len(first.markers), 1)

    def test_original_plan_still_deletes_without_staleness(self):
        first, second, _, _, plan = deletion_fixture()
        delete, calls = recording_delete(first, second)
        result = apply_delete_plan(plan, delete)
        self.assertEqual(result.deleted, 2)
        self.assertEqual(result.changed_targets, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual((first.markers, second.markers), ([], []))

    def test_ui_catches_stale_as_existing_marker_apply_error(self):
        clip = PyClip("Private clip", (PyMarker(),))
        events = {"dialogs": [], "deleted": []}

        def show_in_dialog(title, message, dialog_type, buttons, cancel_button=""):
            events["dialogs"].append((dialog_type, message))
            if dialog_type == "warning":
                # Simulate a user/host change *after* the preview dialog.
                clip.markers.append(PyMarker())
                return "Delete Markers"
            return "OK"

        flame = types.SimpleNamespace(
            messages=types.SimpleNamespace(
                show_in_dialog=show_in_dialog,
                show_in_console=lambda *args: None,
            ),
            delete=lambda marker, confirm=False: events["deleted"].append(marker),
        )
        with patch.dict(sys.modules, {"flame": flame}):
            show_delete_markers((clip,))
        self.assertEqual(events["deleted"], [])
        self.assertEqual([kind for kind, _ in events["dialogs"]], ["warning", "error"])
        self.assertIn("Deleted before failure: 0", events["dialogs"][-1][1])


if __name__ == "__main__":
    unittest.main()
