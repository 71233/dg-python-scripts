"""Host-free tests for proposed Flame 2026 callback-selection contract."""

import builtins
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from dg_python_scripts.actions.selection_contract import (
    HOOK_TO_CONTEXT, CALLBACK_PHASES, SelectionPolicy,
    SelectionReview, inspect_hook_selection,
)


class PyClip:
    pass


class PySequence:
    pass


class PySegment:
    pass


class PyNode:
    pass


class ExplodingProxy:
    def __getattribute__(self, _):
        raise AssertionError("never touch Flame instance attributes")

    def __iter__(self):
        raise AssertionError("never iterate an object")

    def __bool__(self):
        raise AssertionError("never coerce Flame object to bool")

    def __eq__(self, _):
        raise AssertionError("never compare Flame objects")

    def __repr__(self):
        raise AssertionError("never log Flame objects")


class SelectionContractTests(unittest.TestCase):
    def inspect(self, selection=(), hook="get_media_panel_custom_ui_actions",
                phase="execute", policy=SelectionPolicy(), expected_context=None):
        return inspect_hook_selection(hook_name=hook, phase=phase,
                                      selection=selection, policy=policy,
                                      expected_context=expected_context)

    def blocked(self, code, **kwargs):
        r = self.inspect(**kwargs)
        self.assertEqual(r.status, "BLOCKED", r)
        self.assertEqual(r.next_step, "MANUAL_RECONCILIATION")
        self.assertEqual(r.findings, (code,))
        self.assertEqual(r.items, ())
        return r

    def test_official_seven_hook_contexts(self):
        self.assertEqual(HOOK_TO_CONTEXT, {
            "get_main_menu_custom_ui_actions": "main_menu",
            "get_media_panel_custom_ui_actions": "media_panel",
            "get_mediahub_files_custom_ui_actions": "mediahub_files",
            "get_mediahub_archives_custom_ui_actions": "mediahub_archives",
            "get_timeline_custom_ui_actions": "timeline",
            "get_batch_custom_ui_actions": "batch",
            "get_action_custom_ui_actions": "action",
        })
        self.assertEqual(CALLBACK_PHASES, {"isVisible", "isEnabled", "execute"})
        for hook, context in HOOK_TO_CONTEXT.items():
            for phase in CALLBACK_PHASES:
                with self.subTest(hook=hook, phase=phase):
                    r = self.inspect(hook=hook, phase=phase, selection=(PyClip(),))
                    self.assertEqual((r.status, r.context, r.phase),
                                     ("PREVIEW_ONLY", context, phase))

    def test_empty_selection_allowed_by_default(self):
        r = self.inspect(())
        self.assertEqual((r.status, r.count, r.items, r.next_step),
                         ("PREVIEW_ONLY", 0, (), "NO_CHANGE"))

    def test_single_selection_preserves_object_identity(self):
        clip = PyClip()
        r = self.inspect((clip,))
        self.assertIs(r.items[0], clip)
        self.assertEqual(r.count, 1)

    def test_multiple_selection_order_preserved(self):
        a, b = PyClip(), PySequence()
        r = self.inspect((b, a))
        self.assertEqual(r.items, (b, a))
        self.assertIs(r.items[0], b)

    def test_context_checked_against_hook(self):
        r = self.inspect(expected_context="media_panel")
        self.assertEqual(r.status, "PREVIEW_ONLY")
        self.blocked("context_mismatch", expected_context="timeline")
        self.blocked("context_mismatch", expected_context=5)

    def test_unknown_hook_and_phase_block(self):
        self.blocked("unsupported_hook", hook="get_unknown_custom_ui_actions")
        self.blocked("unsupported_hook", hook=object())
        self.blocked("unsupported_callback_phase", phase="other")
        self.blocked("unsupported_callback_phase", phase=object())

    def test_wrong_payload_shapes_block_without_consuming(self):
        class BadIterable:
            def __iter__(self):
                raise AssertionError("untrusted iterable consumed")
        for payload in (None, [], [PyClip()], {}, "clip", b"clip", BadIterable(),
                        (PyClip() for _ in range(1))):
            with self.subTest(kind=type(payload).__name__):
                self.blocked("selection_not_plain_tuple", selection=payload)

    def test_tuple_subclass_not_accepted(self):
        class Subclass(tuple):
            def __iter__(self):
                raise AssertionError("subclass side effect")
        self.blocked("selection_not_plain_tuple", selection=Subclass((PyClip(),)))

    def test_rejects_none_and_primitive_items(self):
        for item in (None, "text", b"bytes", bytearray(b"x"), memoryview(b"x"),
                     1, True, 1.5, 1+2j, [], (), {}, {1}, frozenset({1}), range(2)):
            with self.subTest(kind=type(item).__name__):
                self.blocked("invalid_selection_item", selection=(item,))

    def test_rejects_primitive_subclasses(self):
        class NotAFlameObject(str):
            pass
        self.blocked("invalid_selection_item", selection=(NotAFlameObject("x"),))

    def test_duplicate_identity_blocked_without_equality(self):
        obj = ExplodingProxy()
        self.blocked("duplicate_selection_item", selection=(obj, obj))

    def test_distinct_opaque_proxies_allowed_without_attribute_access(self):
        a, b = ExplodingProxy(), ExplodingProxy()
        r = self.inspect((a, b))
        self.assertEqual(r.status, "PREVIEW_ONLY")
        self.assertEqual(r.count, 2)

    def test_mixed_types_can_be_rejected_for_specific_actions(self):
        policy = SelectionPolicy(allow_mixed_types=False)
        self.blocked("mixed_selection_types", selection=(PyClip(), PySequence()), policy=policy)
        self.assertEqual(self.inspect((PyClip(), PyClip()), policy=policy).status,
                         "PREVIEW_ONLY")

    def test_explicit_type_allowlist_optional(self):
        policy = SelectionPolicy(allowed_type_names=frozenset({"PyClip", "PySequence"}))
        self.assertEqual(self.inspect((PyClip(), PySequence()), policy=policy).status,
                         "PREVIEW_ONLY")
        self.blocked("unsupported_selection_type", selection=(PyNode(),), policy=policy)

    def test_timeline_segment_policy(self):
        policy = SelectionPolicy(min_items=1, allowed_type_names=frozenset({"PySegment"}))
        self.assertEqual(self.inspect((PySegment(),), hook="get_timeline_custom_ui_actions",
                                      policy=policy).status, "PREVIEW_ONLY")
        self.blocked("unsupported_selection_type", selection=(PyClip(),),
                     hook="get_timeline_custom_ui_actions", policy=policy)

    def test_empty_required_selection_blocks(self):
        self.blocked("selection_below_minimum", policy=SelectionPolicy(min_items=1))

    def test_limited_count_rejects_extra_without_accessing_items(self):
        self.blocked("selection_above_maximum", selection=(PyClip(), PyClip()),
                     policy=SelectionPolicy(max_items=1))

    def test_default_hard_limit(self):
        self.assertEqual(self.inspect(tuple(PyClip() for _ in range(256))).status,
                         "PREVIEW_ONLY")
        self.blocked("selection_above_maximum",
                     selection=tuple(PyClip() for _ in range(257)))

    def test_invalid_policy_fail_closed(self):
        invalid = (
            SelectionPolicy(min_items=True), SelectionPolicy(max_items=257),
            SelectionPolicy(min_items=2, max_items=1), SelectionPolicy(min_items=-1),
            SelectionPolicy(allow_mixed_types="yes"),
            SelectionPolicy(allowed_type_names=frozenset()),
            SelectionPolicy(allowed_type_names={"PyClip"}),
            SelectionPolicy(allowed_type_names=frozenset({"Py Clip"})),
            SelectionPolicy(allowed_type_names=frozenset({2})),
            SelectionPolicy(allowed_type_names=frozenset({"name/secret"})),
        )
        for policy in invalid:
            with self.subTest(policy=repr(policy)):
                self.blocked("invalid_selection_policy", policy=policy)
        self.blocked("invalid_selection_policy", policy={})

    def test_hostile_policy_subclass_not_inspected(self):
        class Hostile(SelectionPolicy):
            def __getattribute__(self, _):
                raise AssertionError("never read subclass")
        self.blocked("invalid_selection_policy", policy=Hostile())

    def test_invalid_hook_blocks_before_touching_payload(self):
        class Evil:
            def __iter__(self):
                raise AssertionError("not read")
        self.blocked("unsupported_hook", hook="not_a_hook", selection=Evil())

    def test_report_redacts_opaque_objects(self):
        clip = ExplodingProxy()
        result = self.inspect((clip,))
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertNotIn("ExplodingProxy", repr(result))
        self.assertNotIn("object at", repr(result))
        self.assertEqual(SelectionReview((), count=1).status, "PREVIEW_ONLY")

    def test_no_selected_property_or_global_flame_selection_read(self):
        clip = ExplodingProxy()
        with patch.object(builtins, "open", side_effect=AssertionError("disk I/O")), \
             patch.object(Path, "resolve", side_effect=AssertionError("disk I/O")):
            self.assertEqual(self.inspect((clip,)).status, "PREVIEW_ONLY")
        self.assertNotIn("flame", sys.modules)
        self.assertNotIn("PySide6", sys.modules)

    def test_predicate_and_execute_never_reuse_cached_snapshot(self):
        first, second = PyClip(), PyClip()
        predicate = self.inspect((first,), phase="isVisible")
        execute = self.inspect((second,), phase="execute")
        self.assertIs(predicate.items[0], first)
        self.assertIs(execute.items[0], second)
        self.assertIsNot(predicate.items[0], execute.items[0])

    def test_review_does_not_execute_action_or_mutate_object(self):
        a = ExplodingProxy()
        report = self.inspect((a,))
        self.assertEqual(report.next_step, "NO_CHANGE")
        self.assertFalse(hasattr(report, "apply"))
        self.assertFalse(hasattr(report, "execute"))
        self.assertFalse(hasattr(report, "install"))


if __name__ == "__main__":
    unittest.main()
