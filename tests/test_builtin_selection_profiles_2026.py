"""G2-only synthetic checks for existing DGpy action selection contracts."""

from dataclasses import FrozenInstanceError
from types import MappingProxyType
import builtins
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from dg_python_scripts.actions.builtin_selection_profiles import (
    BUILTIN_SELECTION_PROFILES,
    BuiltinSelectionReview,
    inspect_builtin_selection,
)


class PyClip:
    pass


class PySequence:
    pass


class PyReel:
    pass


class PyNode:
    pass


class PyBatchIteration:
    pass


class Unknown:
    pass


class ExplosiveProxy:
    def __getattribute__(self, name):
        raise AssertionError("host object property accessed")

    def __repr__(self):
        raise AssertionError("host object repr used")

    def __eq__(self, other):
        raise AssertionError("host object equality used")

    def __bool__(self):
        raise AssertionError("host object truthiness used")

    def __iter__(self):
        raise AssertionError("host object iterator used")


MAIN = "get_main_menu_custom_ui_actions"
MEDIA = "get_media_panel_custom_ui_actions"
TIMELINE = "get_timeline_custom_ui_actions"
BATCH = "get_batch_custom_ui_actions"
ACTION = "get_action_custom_ui_actions"


class BuiltinProfileTests(unittest.TestCase):
    def review(self, action="dgpy.rename", hook=MEDIA, selection=None,
               phase="execute"):
        if selection is None:
            selection = (PyClip(),)
        return inspect_builtin_selection(
            action_id=action, hook_name=hook, phase=phase,
            selection=selection,
        )

    def assert_blocked(self, code, **kwargs):
        report = self.review(**kwargs)
        self.assertEqual(report.status, "BLOCKED")
        self.assertEqual(report.findings, (code,))
        self.assertEqual(report.next_step, "MANUAL_RECONCILIATION")
        self.assertFalse(hasattr(report, "execute"))
        self.assertFalse(hasattr(report, "apply"))
        return report

    def test_three_known_builtins_only(self):
        self.assertEqual(set(BUILTIN_SELECTION_PROFILES), {
            "dgpy.about", "dgpy.rename", "dgpy.delete_markers",
        })
        self.assertIsInstance(BUILTIN_SELECTION_PROFILES, MappingProxyType)

    def test_mapping_cannot_be_modified(self):
        with self.assertRaises(TypeError):
            BUILTIN_SELECTION_PROFILES["dgpy.new"] = object()
        with self.assertRaises(FrozenInstanceError):
            BUILTIN_SELECTION_PROFILES["dgpy.rename"].contexts = frozenset()

    def test_action_contexts_agree_with_existing_builtin_registry(self):
        # This import deliberately does not call any action or Hook.
        # In a partial fixture-only sandbox the complete registry is absent;
        # full Public CI runs this against the actual existing code.
        try:
            from dg_python_scripts.actions.main_menu import register_builtin_actions
            from dg_python_scripts.actions.registry import ActionRegistry
        except ModuleNotFoundError as error:
            if error.name in {
                "dg_python_scripts.actions.main_menu",
                "dg_python_scripts.actions.registry",
            }:
                self.skipTest("requires full Public source tree")
            raise
        registry = ActionRegistry()
        register_builtin_actions(registry)
        actions = {a.id: a for a in registry.actions()}
        self.assertEqual(set(actions), set(BUILTIN_SELECTION_PROFILES))
        for action_id, action in actions.items():
            with self.subTest(action_id=action_id):
                self.assertEqual(
                    BUILTIN_SELECTION_PROFILES[action_id].contexts,
                    frozenset(action.contexts),
                )

    def test_rename_contexts_use_capability_not_type_names(self):
        profile = BUILTIN_SELECTION_PROFILES["dgpy.rename"]
        self.assertEqual(profile.contexts, {"media_panel", "timeline", "batch", "action"})
        self.assertIsNone(profile.candidate_type_hints)
        self.assertTrue(profile.requires_host_capability_check)

    def test_rename_selected_opaque_objects_preview_only(self):
        for hook in (MEDIA, TIMELINE, BATCH, ACTION):
            with self.subTest(hook=hook):
                result = self.review(hook=hook, selection=(ExplosiveProxy(),))
                self.assertEqual(result.status, "PREVIEW_ONLY")
                self.assertEqual(result.selection_count, 1)
                self.assertIsNone(result.candidate_type_hint_count)
                self.assertTrue(result.requires_host_capability_check)
                self.assertEqual(result.next_step, "NO_CHANGE")

    def test_rename_empty_rejected(self):
        self.assert_blocked("selection_below_minimum", selection=())

    def test_rename_does_not_guess_batch_iteration_capability(self):
        # The existing rename.probe_target rejects PyBatchIteration later.
        # A shallow callback review must not pretend it checked capability.
        result = self.review(hook=BATCH, selection=(PyBatchIteration(),))
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertTrue(result.requires_host_capability_check)
        self.assertIsNone(result.candidate_type_hint_count)

    def test_rename_does_not_read_name_getter_or_setter(self):
        result = self.review(selection=(ExplosiveProxy(),))
        self.assertEqual(result.status, "PREVIEW_ONLY")

    def test_rename_mixed_and_multiple_are_not_dropped(self):
        selection = (PyClip(), PySequence(), PyNode())
        result = self.review(selection=selection)
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertEqual(result.selection_count, 3)

    def test_about_main_menu_allows_empty_selection(self):
        result = self.review(action="dgpy.about", hook=MAIN, selection=())
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertFalse(result.requires_host_capability_check)
        self.assertEqual(result.candidate_type_hint_count, 0)

    def test_about_does_not_require_selection_to_be_empty(self):
        result = self.review(action="dgpy.about", hook=MAIN,
                             selection=(PyClip(), PySequence()))
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertEqual(result.selection_count, 2)
        self.assertEqual(result.candidate_type_hint_count, 0)

    def test_about_not_available_in_other_contexts(self):
        self.assert_blocked("action_context_mismatch", action="dgpy.about",
                            hook=MEDIA, selection=())

    def test_marker_action_media_panel_only(self):
        self.assertEqual(BUILTIN_SELECTION_PROFILES["dgpy.delete_markers"].contexts,
                         {"media_panel"})
        self.assert_blocked("action_context_mismatch", action="dgpy.delete_markers",
                            hook=TIMELINE, selection=(PyClip(),))

    def test_marker_type_hints_match_current_implementation(self):
        self.assertEqual(
            BUILTIN_SELECTION_PROFILES["dgpy.delete_markers"].candidate_type_hints,
            {"PyClip", "PySequence", "PyReel"},
        )

    def test_marker_clip_sequence_reel_are_unverified_hints(self):
        for item in (PyClip(), PySequence(), PyReel()):
            with self.subTest(item=type(item).__name__):
                result = self.review(action="dgpy.delete_markers", selection=(item,))
                self.assertEqual(result.status, "PREVIEW_ONLY")
                self.assertEqual(result.candidate_type_hint_count, 1)
                self.assertTrue(result.requires_host_capability_check)

    def test_marker_empty_rejected(self):
        self.assert_blocked("selection_below_minimum", action="dgpy.delete_markers",
                            selection=())

    def test_marker_unsupported_type_only_rejected(self):
        self.assert_blocked("no_matching_type_hint", action="dgpy.delete_markers",
                            selection=(PyNode(), Unknown()))

    def test_marker_mixed_selection_keeps_unrelated_items_in_counts(self):
        result = self.review(action="dgpy.delete_markers",
                             selection=(PyNode(), PyClip(), PySequence(), Unknown()))
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertEqual(result.selection_count, 4)
        self.assertEqual(result.candidate_type_hint_count, 2)

    def test_marker_reel_without_children_is_not_proven_actionable(self):
        result = self.review(action="dgpy.delete_markers", selection=(PyReel(),))
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertTrue(result.requires_host_capability_check)
        self.assertEqual(result.next_step, "NO_CHANGE")

    def test_marker_spoofed_type_name_is_not_flame_authorization(self):
        Spoof = type("PyClip", (), {})
        report = self.review(action="dgpy.delete_markers", selection=(Spoof(),))
        self.assertEqual(report.status, "PREVIEW_ONLY")
        self.assertTrue(report.requires_host_capability_check)
        self.assertFalse(hasattr(report, "execute"))

    def test_marker_two_reels_and_clip_count_only_hints(self):
        report = self.review(action="dgpy.delete_markers",
                             selection=(PyReel(), PyReel(), PyClip(), PyNode()))
        self.assertEqual(report.candidate_type_hint_count, 3)
        self.assertEqual(report.selection_count, 4)

    def test_marker_no_marker_attribute_is_inspected(self):
        class PyClip:
            def __getattribute__(self, _):
                raise AssertionError("markers should not be read")
        report = self.review(action="dgpy.delete_markers", selection=(PyClip(),))
        self.assertEqual(report.status, "PREVIEW_ONLY")
        self.assertTrue(report.requires_host_capability_check)

    def test_unknown_action_fails_before_accessing_selection(self):
        class Evil:
            def __getattribute__(self, _):
                raise AssertionError("selection inspected")
        self.assert_blocked("unsupported_builtin_action", action="external.new",
                            selection=Evil())
        self.assert_blocked("unsupported_builtin_action", action=object(),
                            selection=Evil())

    def test_unknown_hook_and_wrong_context_fail_closed(self):
        self.assert_blocked("unsupported_hook", hook="get_unknown_custom_ui_actions")
        self.assert_blocked("action_context_mismatch", action="dgpy.rename",
                            hook=MAIN)

    def test_invalid_phase_is_not_overlooked(self):
        self.assert_blocked("unsupported_callback_phase", phase="clicked")
        self.assert_blocked("unsupported_callback_phase", phase=0)

    def test_hostile_tuple_subclass_rejected(self):
        class Bad(tuple):
            def __iter__(self):
                raise AssertionError("hostile tuple iterated")
        self.assert_blocked("selection_not_plain_tuple", selection=Bad((PyClip(),)))

    def test_primitive_and_duplicate_selection_rejected(self):
        self.assert_blocked("invalid_selection_item", selection=("private",))
        item = ExplosiveProxy()
        self.assert_blocked("duplicate_selection_item", selection=(item, item))

    def test_bounded_selection_rejects_257_items(self):
        self.assert_blocked("selection_above_maximum",
                            selection=tuple(PyClip() for _ in range(257)))

    def test_phase_arguments_remain_independent(self):
        a, b = PyClip(), PyClip()
        visible = self.review(action="dgpy.delete_markers", phase="isVisible",
                              selection=(a,))
        execute = self.review(action="dgpy.delete_markers", phase="execute",
                              selection=(b,))
        self.assertEqual(visible.phase, "isVisible")
        self.assertEqual(execute.phase, "execute")
        self.assertEqual(visible.selection_count, 1)
        self.assertEqual(execute.selection_count, 1)
        self.assertFalse(hasattr(visible, "items"))

    def test_result_does_not_leak_proxy_or_private_name(self):
        item = ExplosiveProxy()
        report = self.review(action="dgpy.rename", selection=(item,))
        text = repr(report)
        self.assertNotIn("ExplosiveProxy", text)
        self.assertNotIn("object at", text)
        self.assertNotIn("private", text)

    def test_no_filesystem_or_flame_host_import(self):
        with patch.object(builtins, "open", side_effect=AssertionError("file I/O")), \
             patch.object(Path, "resolve", side_effect=AssertionError("file I/O")):
            result = self.review(action="dgpy.delete_markers",
                                 selection=(ExplosiveProxy(), PyReel()))
            self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertNotIn("flame", sys.modules)
        self.assertNotIn("PySide6", sys.modules)

    def test_reports_cannot_authorize_action_execution(self):
        report = self.review()
        self.assertEqual(report.next_step, "NO_CHANGE")
        for method in ("execute", "apply", "disable", "restore", "install", "delete"):
            self.assertFalse(hasattr(report, method))
        self.assertIsInstance(BuiltinSelectionReview((), "media_panel"), BuiltinSelectionReview)


if __name__ == "__main__":
    unittest.main()
