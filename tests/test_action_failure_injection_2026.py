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
from dg_python_scripts.ui.rename import _apply_current_plan


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

    def test_final_failure_then_rollback_restores_both_targets(self):
        first = PyClip("First")
        second = PyClip("Second", name_failure="final_after_write")
        with self.assertRaises(RenameApplyError) as cm:
            apply_plan(build_plan((first, second), "New_{index}"))
        self.assertEqual((first.name.value, second.name.value), ("First", "Second"))
        self.assertEqual(cm.exception.rollback_errors, ())

    def test_final_rollback_rejection_is_reported_without_success(self):
        class RejectOriginalRestore(FakeName):
            def set_value(self, new_value):
                if new_value == self.original and self.value != self.original:
                    self.calls.append(new_value)
                    raise RuntimeError("injected restore rejection")
                return super().set_value(new_value)

        first = PyClip("First")
        first.name = RejectOriginalRestore("First")
        second = PyClip("Second", name_failure="final_after_write")
        with self.assertRaises(RenameApplyError) as cm:
            apply_plan(build_plan((first, second), "New_{index}"))
        self.assertTrue(cm.exception.rollback_errors)
        self.assertIn("restore rejection", str(cm.exception))
        self.assertTrue(first.name.value.startswith("__DGPY_ROLLBACK_"))
        self.assertEqual(second.name.value, "Second")

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


class RenameRollbackAuditTests(unittest.TestCase):
    def test_temp_rollback_later_restore_changes_already_restored_row(self):
        first = PyClip("First")
        second = PyClip("Second", name_failure="temp_after_write")

        class ChangeEarlierRestoredName(FakeName):
            def set_value(self, new_value):
                super().set_value(new_value)
                if new_value == self.original:
                    second.name.value = "Changed during rollback"

        first.name = ChangeEarlierRestoredName("First")
        with self.assertRaises(RenameApplyError) as cm:
            apply_plan(build_plan((first, second), "New_{index}"))
        self.assertEqual(first.name.value, "First")
        self.assertEqual(second.name.value, "Changed during rollback")
        self.assertTrue(any("Original name not restored" in issue
                            and "'Second'" in issue
                            for issue in cm.exception.rollback_errors))

    def test_final_rollback_later_restore_changes_already_restored_row(self):
        first = PyClip("First")
        second = PyClip("Second")

        class ChangeFirstOnRestore(FakeName):
            def set_value(self, new_value):
                super().set_value(new_value)
                if new_value == self.original:
                    first.name.value = "Changed during rollback"

        second.name = ChangeFirstOnRestore("Second", failure="final_after_write")
        with self.assertRaises(RenameApplyError) as cm:
            apply_plan(build_plan((first, second), "New_{index}"))
        self.assertEqual(second.name.value, "Second")
        self.assertEqual(first.name.value, "Changed during rollback")
        self.assertTrue(any("Original name not restored" in issue
                            and "'First'" in issue
                            for issue in cm.exception.rollback_errors))

    def test_final_rollback_audit_unreadable_after_successful_readback(self):
        class DenyAfterRestoreReadback(FakeName):
            restored = False
            restored_reads = 0

            def set_value(self, new_value):
                super().set_value(new_value)
                if new_value == self.original:
                    self.restored = True

            def get_value(self):
                if self.restored:
                    self.restored_reads += 1
                    if self.restored_reads > 1:
                        raise RuntimeError("injected final audit read failure")
                return super().get_value()

        first = PyClip("First")
        first.name = DenyAfterRestoreReadback("First")
        second = PyClip("Second", name_failure="final_after_write")
        with self.assertRaises(RenameApplyError) as cm:
            apply_plan(build_plan((first, second), "New_{index}"))
        self.assertEqual(first.name.value, "First")
        self.assertTrue(any("Could not verify original name 'First'" in issue
                            for issue in cm.exception.rollback_errors))

    def test_temp_failure_audits_unattempted_row_without_writing_it(self):
        third = PyClip("Third")

        class FailAndChangeUnattempted(FakeName):
            def set_value(self, new_value):
                super().set_value(new_value)
                if new_value.startswith("__DGPY_TMP_"):
                    third.name.value = "Changed outside attempted rows"
                    raise RuntimeError("injected temporary failure")

        first = PyClip("First")
        first.name = FailAndChangeUnattempted("First")
        second = PyClip("Second")
        with self.assertRaises(RenameApplyError) as cm:
            apply_plan(build_plan((first, second, third), "New_{index}"))
        self.assertEqual(first.name.value, "First")
        self.assertEqual(second.name.calls, [])
        self.assertEqual(third.name.calls, [])
        self.assertEqual(third.name.value, "Changed outside attempted rows")
        self.assertTrue(any("Original name not restored" in issue
                            and "'Third'" in issue
                            for issue in cm.exception.rollback_errors))


class RenameApplyDialogTests(unittest.TestCase):
    """Exercise the actual apply callback with fake UI and name attributes."""

    def _setup(self, clip):
        self.state = {"plan": build_plan((clip,), "New_{index}"), "blocked": False}
        self.events = []
        self.clip = clip
        self.button = types.SimpleNamespace(
            setEnabled=lambda enabled: self.events.append(("enabled", enabled))
        )
        self.dialog = types.SimpleNamespace(
            accept=lambda: self.events.append(("accept", None)),
            reject=lambda: self.events.append(("reject", None)),
        )

    def _show_error(self, message):
        self.events.append(("error", message))
        # A nested click from a modal event loop cannot reapply the plan.
        self._apply()

    def _refresh(self):
        self.events.append(("refresh", None))
        self.state["plan"] = build_plan((self.clip,), "New_{index}")

    def _apply(self):
        _apply_current_plan(self.state, self.button, self.dialog,
                            self._show_error, self._refresh)

    def test_apply_failure_with_unrestored_temp_name_closes_without_repreview(self):
        class RejectRestore(FakeName):
            def set_value(self, new_value):
                if new_value == self.original:
                    raise RuntimeError("restore rejected")
                return super().set_value(new_value)

        clip = PyClip("Original")
        clip.name = RejectRestore("Original", failure="temp_after_write")
        self._setup(clip)
        self._apply()
        self.assertTrue(clip.name.value.startswith("__DGPY_TMP_"))
        self.assertTrue(self.state["blocked"])
        self.assertIsNone(self.state["plan"])
        self.assertEqual([kind for kind, _ in self.events],
                         ["enabled", "error", "reject"])
        self.assertIn("Rollback issues", self.events[1][1])
        self.assertIn("temporary names may remain", self.events[1][1])
        self.assertIn("Restoration is not guaranteed.", self.events[1][1])
        calls = list(clip.name.calls)
        # Even if a caller supplies a new plan, a blocked dialog cannot apply.
        self.state["plan"] = build_plan((clip,), "Another")
        self._apply()
        self.assertEqual(clip.name.calls, calls)

    def test_apply_failure_with_successful_compensation_still_closes(self):
        clip = PyClip("Original", name_failure="temp_after_write")
        self._setup(clip)
        self._apply()
        self.assertEqual(clip.name.value, "Original")
        self.assertTrue(self.state["blocked"])
        self.assertEqual([kind for kind, _ in self.events],
                         ["enabled", "error", "reject"])
        self.assertIn("Restoration is not guaranteed.", self.events[1][1])

    def test_stale_preview_refreshes_without_rename_or_close(self):
        clip = PyClip("Original")
        self._setup(clip)
        clip.name.value = "Changed"
        self._apply()
        self.assertEqual(clip.name.calls, [])
        self.assertFalse(self.state["blocked"])
        self.assertEqual([kind for kind, _ in self.events],
                         ["enabled", "error", "refresh"])
        self.assertIn("DGpy made no rename calls.", self.events[1][1])
        self.assertEqual(self.state["plan"].ready_rows[0].original_name, "Changed")

    def test_healthy_apply_accepts_once_and_consumes_preview(self):
        clip = PyClip("Original")
        self._setup(clip)
        self._apply()
        self._apply()
        self.assertEqual(clip.name.value, "New_1")
        self.assertTrue(self.state["blocked"])
        self.assertIsNone(self.state["plan"])
        self.assertEqual([kind for kind, _ in self.events], ["enabled", "accept"])


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

    def test_callback_failure_after_deleting_last_marker_is_reported(self):
        marker = PyMarker()
        clip = PyClip("Private clip", (marker,))
        plan = build_delete_plan((clip,))
        calls = []

        def delete_then_raise(candidate):
            calls.append(candidate)
            clip.markers.remove(candidate)
            raise RuntimeError("injected callback failure after removal")

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_then_raise)
        self.assertEqual(calls, [marker])
        self.assertEqual(clip.markers, [])
        self.assertEqual(cm.exception.deleted, 1)
        self.assertIn("RuntimeError", str(cm.exception))

    def test_callback_failure_after_delete_across_targets_is_not_hidden(self):
        first, second, first_marker, second_marker, plan = deletion_fixture()
        normal_delete, calls = recording_delete(first, second)

        def delete_with_error(marker):
            normal_delete(marker)
            if marker is first_marker:
                raise RuntimeError("injected failure after first removal")

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_with_error)
        self.assertEqual(calls, [first_marker])
        self.assertEqual((first.markers, second.markers), ([], [second_marker]))
        self.assertEqual(cm.exception.deleted, 1)
        self.assertIn("injected failure", str(cm.exception))

    def test_change_after_precheck_must_not_report_full_success(self):
        # This mutation occurs in the first delete callback, hence AFTER
        # the all-target recheck. No Python-only check can make it atomic.
        first, second, first_marker, _, plan = deletion_fixture()
        normal_delete, calls = recording_delete(first, second)
        new_marker = PyMarker()

        def deletion_with_race(marker):
            if marker is first_marker:
                second.markers.append(new_marker)
            normal_delete(marker)

        with self.assertRaises(MarkerApplyError):
            apply_delete_plan(plan, deletion_with_race)
        self.assertEqual(calls, [first_marker])
        self.assertEqual(first.markers, [])
        self.assertEqual(len(second.markers), 2)
        self.assertTrue(any(item is new_marker for item in second.markers))
        # The first marker has already been deleted: still a partial change.
        # The new per-target guard limits further deletions; it is not atomic.

    def test_late_second_target_change_stops_before_second_delete(self):
        first, second, first_marker, second_marker, plan = deletion_fixture()
        normal_delete, calls = recording_delete(first, second)
        injected = PyMarker()

        def delete_with_late_change(marker):
            normal_delete(marker)
            if marker is first_marker:
                second.markers.append(injected)

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_with_late_change)
        self.assertNotIsInstance(cm.exception, StaleMarkerDeleteError)
        self.assertEqual(cm.exception.deleted, 1)
        self.assertEqual(calls, [first_marker])
        self.assertEqual(first.markers, [])
        self.assertEqual(second.markers, [second_marker, injected])

    def test_late_second_target_unreadable_stops_before_second_delete(self):
        first_marker, second_marker = PyMarker(), PyMarker()
        first = PyClip("First", (first_marker,))
        second = PySequence("Second", (second_marker,))
        plan = build_delete_plan((first, second))
        self.assertEqual(len(plan.targets), 2)
        normal_delete, calls = recording_delete(first, second)

        def delete_then_deny(marker):
            normal_delete(marker)
            if marker is first_marker:
                second.deny_read = True

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_then_deny)
        self.assertEqual(cm.exception.deleted, 1)
        self.assertEqual(calls, [first_marker])
        self.assertEqual(first.markers, [])
        self.assertEqual(vars(second)["markers"], [second_marker])

    def test_callback_failure_before_removal_aborts_remaining_markers(self):
        a, b, c = PyMarker(), PyMarker(), PyMarker()
        first = PyClip("First", (a, b))
        second = PyClip("Second", (c,))
        plan = build_delete_plan((first, second))
        called = []

        def rejected_delete(marker):
            called.append(marker)
            raise RuntimeError("injected rejection before mutation")

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, rejected_delete)
        self.assertEqual(cm.exception.deleted, 0)
        self.assertEqual(called, [a])
        self.assertEqual(first.markers, [a, b])
        self.assertEqual(second.markers, [c])

    def test_callback_failure_after_removal_aborts_remaining_markers(self):
        a, b, c = PyMarker(), PyMarker(), PyMarker()
        first = PyClip("First", (a, b))
        second = PyClip("Second", (c,))
        plan = build_delete_plan((first, second))
        called = []

        def delete_then_raise(marker):
            called.append(marker)
            first.markers.remove(marker)
            raise RuntimeError("injected mutation then exception")

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_then_raise)
        self.assertEqual(cm.exception.deleted, 1)
        self.assertEqual(called, [a])
        self.assertEqual(first.markers, [b])
        self.assertEqual(second.markers, [c])

    def test_same_target_replaced_next_marker_blocks_before_second_delete(self):
        first, second, replacement = PyMarker(), PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))
        plan = build_delete_plan((clip,))
        calls = []

        def delete_with_replacement(marker):
            calls.append(marker)
            if marker is first:
                clip.markers[:] = [replacement]

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_with_replacement)
        self.assertNotIsInstance(cm.exception, StaleMarkerDeleteError)
        self.assertEqual(calls, [first])
        self.assertEqual(clip.markers, [replacement])
        self.assertIn("during deletion", str(cm.exception))

    def test_same_target_extra_marker_blocks_before_second_delete(self):
        first, second, extra = PyMarker(), PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))
        plan = build_delete_plan((clip,))
        calls = []

        def delete_and_append(marker):
            calls.append(marker)
            clip.markers.remove(marker)
            if marker is first:
                clip.markers.append(extra)

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_and_append)
        self.assertEqual(calls, [first])
        self.assertEqual(clip.markers, [second, extra])
        # Net length can be zero despite a previous successful deletion.
        self.assertEqual(cm.exception.deleted, 0)

    def test_same_target_noop_callback_stops_before_second_delete(self):
        first, second = PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))
        plan = build_delete_plan((clip,))
        calls = []
        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, lambda marker: calls.append(marker))
        self.assertEqual(calls, [first])
        self.assertEqual(clip.markers, [first, second])
        self.assertEqual(cm.exception.deleted, 0)
        self.assertIn("2 marker(s) remain", str(cm.exception))

    def test_same_target_unreadable_after_first_callback_aborts(self):
        first, second = PyMarker(), PyMarker()
        sequence = PySequence("Private", (first, second))
        plan = build_delete_plan((sequence,))
        calls = []

        def delete_then_deny(marker):
            calls.append(marker)
            sequence.markers.remove(marker)
            sequence.deny_read = True

        with self.assertRaises(MarkerApplyError):
            apply_delete_plan(plan, delete_then_deny)
        self.assertEqual(calls, [first])
        self.assertEqual(vars(sequence)["markers"], [second])

    def test_same_target_unexpected_extra_deletion_aborts_next_callback(self):
        first, second = PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))
        plan = build_delete_plan((clip,))
        calls = []

        def delete_both_at_once(marker):
            calls.append(marker)
            clip.markers.clear()

        with self.assertRaises(MarkerApplyError) as cm:
            apply_delete_plan(plan, delete_both_at_once)
        self.assertEqual(calls, [first])
        self.assertEqual(clip.markers, [])
        self.assertEqual(cm.exception.deleted, 2)

    def test_same_target_normal_three_marker_deletion_still_succeeds(self):
        markers = (PyMarker(), PyMarker(), PyMarker())
        clip = PyClip("Private", markers)
        plan = build_delete_plan((clip,))
        delete, calls = recording_delete(clip)
        result = apply_delete_plan(plan, delete)
        self.assertEqual(calls, list(markers))
        self.assertEqual((result.deleted, result.changed_targets), (3, 1))
        self.assertEqual(clip.markers, [])

    def test_recreated_proxy_ref_preflight_stops_with_zero_callbacks(self):
        class PyClip:
            def __init__(self):
                self.name = FakeName("Private")
                self.reads = 0

            @property
            def markers(self):
                self.reads += 1
                # Deliberately create a new proxy on each read. This is
                # NOT an assertion about Flame 2026 real proxy behavior.
                return [PyMarker()]

        clip = PyClip()
        plan = build_delete_plan((clip,))
        calls = []
        with self.assertRaises(StaleMarkerDeleteError) as cm:
            apply_delete_plan(plan, lambda marker: calls.append(marker))
        self.assertEqual(cm.exception.deleted, 0)
        self.assertEqual(calls, [])
        self.assertGreaterEqual(clip.reads, 2)

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
        message = events["dialogs"][-1][1]
        self.assertIn("DGpy made no delete calls.", message)
        self.assertIn("Review the selection and current markers", message)
        self.assertNotIn("Deleted before failure:", message)
        self.assertNotIn("Some markers may already", message)


class MarkerFailureDialogTests(unittest.TestCase):
    """Check the existing dialog through fake Flame callbacks, never the host."""

    def _run_action(self, clip, callback, *, answer="Delete Markers"):
        events = {"dialogs": [], "deleted": [], "console": []}

        def show_in_dialog(title, message, dialog_type, buttons, cancel_button=""):
            events["dialogs"].append((dialog_type, message))
            return answer if dialog_type == "warning" else "OK"

        def delete(marker, confirm=False):
            self.assertFalse(confirm)
            events["deleted"].append(marker)
            callback(marker)

        flame = types.SimpleNamespace(
            messages=types.SimpleNamespace(
                show_in_dialog=show_in_dialog,
                show_in_console=lambda *args: events["console"].append(args),
            ),
            delete=delete,
        )
        with patch.dict(sys.modules, {"flame": flame}):
            show_delete_markers((clip,))
        return events

    def _assert_uncertain_failure(self, events, expected_calls):
        self.assertEqual(events["deleted"], expected_calls)
        self.assertEqual([kind for kind, _ in events["dialogs"]], ["warning", "error"])
        self.assertEqual(events["console"], [])
        message = events["dialogs"][-1][1]
        self.assertIn("The number of deleted markers could not be reliably verified.", message)
        self.assertIn("Some markers may already have been changed or deleted.", message)
        self.assertIn("No automatic restoration was attempted.", message)
        self.assertIn("Inspect the affected clips/sequences", message)
        self.assertNotIn("Deleted before failure:", message)
        self.assertNotIn("DGpy made no delete calls.", message)
        return message

    def test_ui_callback_rejected_before_mutation_has_no_claimed_count(self):
        first, second = PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))

        def reject(marker):
            raise RuntimeError("injected rejection")

        events = self._run_action(clip, reject)
        message = self._assert_uncertain_failure(events, [first])
        self.assertIn("injected rejection", message)
        self.assertEqual(clip.markers, [first, second])

    def test_ui_callback_mutated_then_raised_warns_of_partial_change(self):
        first, second = PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))

        def remove_then_raise(marker):
            clip.markers.remove(marker)
            raise RuntimeError("injected failure after removal")

        events = self._run_action(clip, remove_then_raise)
        message = self._assert_uncertain_failure(events, [first])
        self.assertIn("injected failure after removal", message)
        self.assertEqual(clip.markers, [second])

    def test_ui_net_zero_after_insertion_does_not_claim_zero_deletions(self):
        first, second, extra = PyMarker(), PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))

        def remove_and_insert(marker):
            clip.markers.remove(marker)
            clip.markers.append(extra)

        events = self._run_action(clip, remove_and_insert)
        self._assert_uncertain_failure(events, [first])
        self.assertEqual(clip.markers, [second, extra])

    def test_ui_unreadable_remainder_does_not_claim_zero_deletions(self):
        first, second = PyMarker(), PyMarker()
        clip = PySequence("Private", (first, second))

        def remove_then_deny(marker):
            clip.markers.remove(marker)
            clip.deny_read = True

        events = self._run_action(clip, remove_then_deny)
        message = self._assert_uncertain_failure(events, [first])
        self.assertIn("Could not revalidate remaining markers", message)
        self.assertEqual(vars(clip)["markers"], [second])

    def test_ui_unexpected_multi_deletion_does_not_claim_success_count(self):
        first, second = PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))
        events = self._run_action(clip, lambda marker: clip.markers.clear())
        self._assert_uncertain_failure(events, [first])
        self.assertEqual(clip.markers, [])

    def test_ui_healthy_delete_retains_success_notification(self):
        first, second = PyMarker(), PyMarker()
        clip = PyClip("Private", (first, second))
        events = self._run_action(clip, clip.markers.remove)
        self.assertEqual(events["deleted"], [first, second])
        self.assertEqual(clip.markers, [])
        self.assertEqual([kind for kind, _ in events["dialogs"]], ["warning"])
        self.assertEqual(len(events["console"]), 1)
        self.assertIn("Deleted 2 marker(s) from 1 Clip/Sequence", events["console"][0][0])

    def test_ui_cancel_makes_no_delete_calls(self):
        first = PyMarker()
        clip = PyClip("Private", (first,))
        events = self._run_action(clip, clip.markers.remove, answer="Cancel")
        self.assertEqual(events["deleted"], [])
        self.assertEqual(clip.markers, [first])
        self.assertEqual([kind for kind, _ in events["dialogs"]], ["warning"])
        self.assertEqual(events["console"], [])


if __name__ == "__main__":
    unittest.main()
