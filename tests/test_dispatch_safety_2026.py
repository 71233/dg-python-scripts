"""Independent G2 broker/registry/menu/hook audit; no Flame or Qt runtime.

Existing 2025-observed selection preference remains in test_core.py.
These fake objects do not establish any Flame 2026 proxy contract.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dg_python_scripts import hooks
from dg_python_scripts.actions.menu import build_menu
from dg_python_scripts.actions.registry import ACTION_CONTEXTS, Action, ActionRegistry
from dg_python_scripts.actions.selection import SelectionBroker, SelectionInputError, SelectionPredicateError
from dg_python_scripts.extensions.loader import load_extensions

ROOT = Path(__file__).resolve().parents[1]


class GetterLookupFailure:
    @property
    def get_value(self):
        raise RuntimeError("getter lookup unavailable")


class BrokerAuditTests(unittest.TestCase):
    def test_unreadable_getter_metadata_is_unknown_not_callback_failure(self):
        received = []
        item = SelectionBroker().bind(Action("lookup", "Lookup", received.append), "media_panel")
        target = SimpleNamespace(selected=GetterLookupFailure())
        current = SimpleNamespace(selected=True)
        self.assertTrue(item["isVisible"]((target,)))
        item["execute"]((current,))
        self.assertEqual(received, [(current,)])

    def test_unreadable_getter_replaces_previous_unselected_snapshot(self):
        received = []
        item = SelectionBroker().bind(Action("old", "Old", received.append), "media_panel")
        old = SimpleNamespace(selected=False)
        unreadable = SimpleNamespace(selected=GetterLookupFailure())
        current = SimpleNamespace(selected=True)
        item["isVisible"]((old,))
        item["isEnabled"]((unreadable,))
        item["execute"]((current,))
        self.assertEqual(received, [(current,)])

    def test_contexts_and_actions_do_not_share_snapshots(self):
        received = []
        broker = SelectionBroker()
        action = Action("one", "One", received.append, contexts=("media_panel", "timeline"))
        media = broker.bind(action, "media_panel")
        timeline = broker.bind(action, "timeline")
        other = broker.bind(Action("two", "Two", received.append), "media_panel")
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        media["isVisible"]((target,))
        timeline["execute"]((current,))
        other["execute"]((current,))
        media["execute"]((current,))
        self.assertEqual(received, [(current,), (current,), (target,)])

    def test_latest_predicate_replaces_snapshot(self):
        received = []
        item = SelectionBroker().bind(Action("latest", "Latest", received.append), "media_panel")
        first = SimpleNamespace(selected=False)
        latest = SimpleNamespace(selected=False)
        item["isVisible"]((first,))
        item["isEnabled"]((latest,))
        item["execute"]((object(),))
        self.assertEqual(received, [(latest,)])

    def test_snapshot_consumed_before_execute_callback_raises(self):
        received = []
        def execute(selection):
            received.append(selection)
            raise RuntimeError("action failed")
        item = SelectionBroker().bind(Action("once", "Once", execute), "media_panel")
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        item["isVisible"]((target,))
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "action failed"):
                item["execute"]((current,))
        self.assertEqual(received, [(target,), (current,)])

    def test_unknown_selected_state_uses_execute_on_mismatch(self):
        class BrokenGetter:
            def get_value(self):
                raise RuntimeError("get failed")
        class BrokenBool:
            def __bool__(self):
                raise RuntimeError("bool failed")
        for selected in (None, BrokenGetter(), BrokenBool()):
            with self.subTest(selected_type=type(selected).__name__):
                received = []
                target = SimpleNamespace(selected=selected)
                current = object()
                item = SelectionBroker().bind(Action("unknown", "Unknown", received.append), "media_panel")
                item["isVisible"]((target,))
                item["execute"]((current,))
                self.assertEqual(received, [(current,)])

    def test_execute_does_not_recheck_predicates_characterization(self):
        # Existing behavior, not an authorization policy for destructive actions.
        received, predicates = [], []
        def predicate(selection):
            predicates.append(selection)
            return False
        item = SelectionBroker().bind(
            Action("policy", "Policy", received.append, is_enabled=predicate), "media_panel")
        selection = (object(),)
        self.assertFalse(item["isEnabled"](selection))
        item["execute"](selection)
        self.assertEqual(predicates, [selection])
        self.assertEqual(received, [selection])


class PredicateFailurePolicyTests(unittest.TestCase):
    """G2 callback models; do not assume actual Flame callback ordering."""

    def _assert_blocked(self, item, selection):
        with self.assertRaisesRegex(RuntimeError, "predicate evaluation"):
            item["execute"](selection)

    def test_visibility_exception_blocks_both_snapshot_and_execute_fallback(self):
        received = []
        old = SimpleNamespace(selected=False)
        failed = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)

        def visible(selection):
            if selection[0] is failed:
                raise ValueError("injected visibility failure")
            return True

        broker = SelectionBroker()
        item = broker.bind(
            Action("visible", "Visible", received.append, is_visible=visible),
            "media_panel",
        )
        self.assertTrue(item["isVisible"]((old,)))
        with self.assertRaisesRegex(ValueError, "injected visibility failure"):
            item["isVisible"]((failed,))
        self._assert_blocked(item, (current,))
        self._assert_blocked(item, (failed,))
        self.assertEqual(received, [])
        self.assertEqual(broker._snapshots, {})

    def test_enabled_exception_blocks_until_new_positive_predicate(self):
        received = []
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        fail = True

        def enabled(selection):
            if fail:
                raise RuntimeError("injected enabled failure")
            return True

        item = SelectionBroker().bind(
            Action("enabled", "Enabled", received.append, is_enabled=enabled),
            "media_panel",
        )
        with self.assertRaisesRegex(RuntimeError, "injected enabled failure"):
            item["isEnabled"]((target,))
        self._assert_blocked(item, (current,))
        self._assert_blocked(item, (current,))
        fail = False
        self.assertTrue(item["isEnabled"]((target,)))
        item["execute"]((current,))
        item["execute"]((current,))
        self.assertEqual(received, [(target,), (current,)])

    def test_truth_conversion_exception_is_a_predicate_failure(self):
        received = []

        class BrokenResult:
            def __bool__(self):
                raise ValueError("injected result conversion failure")

        item = SelectionBroker().bind(
            Action("truth", "Truth", received.append,
                   is_enabled=lambda selection: BrokenResult()),
            "media_panel",
        )
        with self.assertRaisesRegex(ValueError, "injected result conversion failure"):
            item["isEnabled"]((SimpleNamespace(selected=False),))
        self._assert_blocked(item, (object(),))
        self.assertEqual(received, [])

    def test_false_after_exception_does_not_clear_failure(self):
        received = []
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        outcomes = iter((ValueError("injected failure"), False, True))

        def enabled(selection):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        item = SelectionBroker().bind(
            Action("recover", "Recover", received.append, is_enabled=enabled),
            "media_panel",
        )
        with self.assertRaisesRegex(ValueError, "injected failure"):
            item["isEnabled"]((target,))
        self.assertFalse(item["isEnabled"]((target,)))
        self._assert_blocked(item, (current,))
        self.assertEqual(received, [])
        self.assertTrue(item["isEnabled"]((target,)))
        item["execute"]((current,))
        self.assertEqual(received, [(target,)])

    def test_failure_is_scoped_to_action_and_context(self):
        received = []
        broker = SelectionBroker()

        def fail(selection):
            raise ValueError("injected failure")

        action = Action("scoped", "Scoped", received.append,
                        contexts=("media_panel", "timeline"), is_enabled=fail)
        media = broker.bind(action, "media_panel")
        timeline = broker.bind(action, "timeline")
        other = broker.bind(Action("other", "Other", received.append), "media_panel")
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        timeline["isVisible"]((target,))
        other["isVisible"]((target,))
        with self.assertRaisesRegex(ValueError, "injected failure"):
            media["isEnabled"]((target,))
        self._assert_blocked(media, (current,))
        timeline["execute"]((current,))
        other["execute"]((current,))
        self.assertEqual(received, [(target,), (target,)])

    def test_no_execute_or_selection_iteration_while_predicate_runs(self):
        received = []

        iterated = []

        class UntouchableSelection:
            def __iter__(self):
                iterated.append(True)
                raise AssertionError("must not inspect execute input")

        def enabled(selection):
            self._assert_blocked(item, UntouchableSelection())
            self.assertEqual(iterated, [])
            return True

        item = SelectionBroker().bind(
            Action("reentry", "Reentry", received.append, is_enabled=enabled),
            "media_panel",
        )
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        self.assertTrue(item["isEnabled"]((target,)))
        self.assertEqual(received, [])
        item["execute"]((current,))
        self.assertEqual(received, [(target,)])

    def test_reentrant_same_key_predicate_failure_leaves_dispatch_blocked(self):
        received = []
        calls = []

        def enabled(selection):
            calls.append(selection)
            item["isVisible"]((SimpleNamespace(selected=False),))
            return True

        item = SelectionBroker().bind(
            Action("nested", "Nested", received.append, is_enabled=enabled),
            "media_panel",
        )
        with self.assertRaisesRegex(RuntimeError, "predicate evaluation"):
            item["isEnabled"]((SimpleNamespace(selected=True),))
        self.assertEqual(len(calls), 1)
        self._assert_blocked(item, (object(),))
        self.assertEqual(received, [])

    def test_failed_predicate_does_not_allow_menu_rebuild_to_clear_block(self):
        received = []
        broker = SelectionBroker()
        registry = ActionRegistry()

        def fail(selection):
            raise ValueError("injected failure")

        registry.register(Action("rebuild", "Rebuild", received.append,
                                 contexts=("media_panel",), is_enabled=fail))
        first = build_menu(registry, "media_panel", broker=broker)[0]["actions"][0]
        with self.assertRaisesRegex(ValueError, "injected failure"):
            first["isEnabled"]((object(),))
        rebuilt = build_menu(registry, "media_panel", broker=broker)[0]["actions"][0]
        self._assert_blocked(rebuilt, (object(),))
        self.assertEqual(received, [])

    def test_false_without_exception_keeps_legacy_selection_preference(self):
        received = []
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        item = SelectionBroker().bind(
            Action("false", "False", received.append, is_enabled=lambda selection: False),
            "media_panel",
        )
        self.assertFalse(item["isEnabled"]((target,)))
        item["execute"]((current,))
        self.assertEqual(received, [(target,)])

    def test_fresh_binding_without_predicate_can_still_execute(self):
        received = []
        selection = (object(),)
        item = SelectionBroker().bind(
            Action("direct", "Direct", received.append), "media_panel"
        )
        item["execute"](selection)
        self.assertEqual(received, [selection])


    def test_other_positive_or_default_phase_cannot_clear_failure(self):
        for visible in (None, lambda selection: True):
            with self.subTest(explicit_visibility=visible is not None):
                received = []
                target = SimpleNamespace(selected=False)
                current = SimpleNamespace(selected=True)
                fail = True

                def enabled(selection):
                    if fail:
                        raise ValueError("injected failure")
                    return True

                item = SelectionBroker().bind(
                    Action("phase", "Phase", received.append,
                           is_visible=visible, is_enabled=enabled),
                    "media_panel",
                )
                with self.assertRaisesRegex(ValueError, "injected failure"):
                    item["isEnabled"]((target,))
                self.assertTrue(item["isVisible"]((current,)))
                self._assert_blocked(item, (current,))
                self.assertEqual(received, [])
                fail = False
                self.assertTrue(item["isEnabled"]((target,)))
                item["execute"]((current,))
                self.assertEqual(received, [(target,)])

    def test_each_failed_phase_must_independently_recover(self):
        received = []
        failed = {"visible", "enabled"}

        def predicate(phase):
            def evaluate(selection):
                if phase in failed:
                    raise ValueError("injected " + phase + " failure")
                return True
            return evaluate

        item = SelectionBroker().bind(
            Action("both", "Both", received.append,
                   is_visible=predicate("visible"), is_enabled=predicate("enabled")),
            "media_panel",
        )
        target = SimpleNamespace(selected=False)
        current = SimpleNamespace(selected=True)
        for phase, callback in (("visible", "isVisible"), ("enabled", "isEnabled")):
            with self.assertRaisesRegex(ValueError, "injected " + phase + " failure"):
                item[callback]((target,))
        failed.remove("visible")
        self.assertTrue(item["isVisible"]((target,)))
        self._assert_blocked(item, (current,))
        self.assertEqual(received, [])
        failed.remove("enabled")
        self.assertTrue(item["isEnabled"]((target,)))
        item["execute"]((current,))
        self.assertEqual(received, [(target,)])


class SelectionInputAuditTests(unittest.TestCase):
    def _binding(self):
        self.received = []
        self.predicates = []
        broker = SelectionBroker()
        item = broker.bind(Action("input", "Input", self.received.append,
                                  is_enabled=lambda selection: self.predicates.append(selection) or True),
                           "media_panel")
        return broker, item

    def test_duplicate_predicate_clears_old_snapshot_and_blocks_until_recovery(self):
        broker, item = self._binding()
        old, current = SimpleNamespace(selected=False), object()
        item["isVisible"]((old,))
        with self.assertRaisesRegex(SelectionInputError, "duplicate"):
            item["isEnabled"]((old, old))
        self.assertEqual(broker._snapshots, {})
        self.assertEqual(self.predicates, [])
        with self.assertRaises(SelectionPredicateError):
            item["execute"]((current,))
        self.assertEqual(self.received, [])
        self.assertTrue(item["isEnabled"]((current,)))
        item["execute"]((current,))
        self.assertEqual(self.received, [(current,)])

    def test_duplicate_execute_never_uses_preferred_snapshot(self):
        broker, item = self._binding()
        old, current = SimpleNamespace(selected=False), object()
        item["isVisible"]((old,))
        with self.assertRaisesRegex(SelectionInputError, "duplicate"):
            item["execute"]((current, current))
        self.assertEqual(self.received, [])
        self.assertEqual(broker._snapshots, {})
        item["execute"]((current,))
        self.assertEqual(self.received, [(current,)])

    def test_equal_identity_sets_with_different_multiplicity_are_rejected(self):
        _, item = self._binding()
        a, b = object(), object()
        item["isVisible"]((a, b))
        with self.assertRaisesRegex(SelectionInputError, "duplicate"):
            item["execute"]((a, a, b))
        self.assertEqual(self.received, [])

    def test_arbitrary_iterables_rejected_without_consumption(self):
        calls = []

        class Hostile:
            def __iter__(self):
                calls.append("iterated")
                raise AssertionError("must not iterate")

        class TupleSubclass(tuple):
            def __iter__(self):
                calls.append("subclass")
                raise AssertionError("must not iterate")

        class ListSubclass(list):
            def __iter__(self):
                calls.append("subclass")
                raise AssertionError("must not iterate")

        for value in (Hostile(), TupleSubclass(), ListSubclass(), None, "clip", {"clip": object()}):
            with self.subTest(kind=type(value).__name__):
                _, item = self._binding()
                with self.assertRaises(SelectionInputError):
                    item["isEnabled"](value)
                self.assertEqual(self.predicates, [])
                _, item = self._binding()
                with self.assertRaises(SelectionInputError):
                    item["execute"](value)
                self.assertEqual(self.received, [])
        self.assertEqual(calls, [])

    def test_failed_execute_does_not_fall_back_to_empty_or_snapshot(self):
        broker, item = self._binding()
        item["isVisible"]((SimpleNamespace(selected=False),))
        with self.assertRaises(SelectionInputError):
            item["execute"](None)
        self.assertEqual(broker._snapshots, {})
        self.assertEqual(self.received, [])

    def test_primitive_items_rejected_before_any_selected_property_access(self):
        calls = []

        class Probe:
            @property
            def selected(self):
                calls.append("selected")
                return False

        class StringSubclass(str):
            pass

        for value in (None, False, 3, "clip", StringSubclass("clip"), [], {}):
            with self.subTest(kind=type(value).__name__):
                _, item = self._binding()
                with self.assertRaises(SelectionInputError):
                    item["isEnabled"]((Probe(), value))
                self.assertEqual(self.predicates, [])
                _, item = self._binding()
                with self.assertRaises(SelectionInputError):
                    item["execute"]((value,))
                self.assertEqual(self.received, [])
        self.assertEqual(calls, [])

    def test_plain_list_and_empty_tuple_keep_legacy_behavior(self):
        _, item = self._binding()
        target, current = SimpleNamespace(selected=False), object()
        self.assertTrue(item["isEnabled"]([target]))
        item["execute"]([current])
        item["execute"](())
        self.assertEqual(self.predicates, [(target,)])
        self.assertEqual(self.received, [(target,), ()])

    def test_distinct_objects_never_compared_by_equality(self):
        class NoCompare:
            selected = True
            def __eq__(self, other):
                raise AssertionError("must not compare objects")
            def __hash__(self):
                raise AssertionError("must not hash objects")

        _, item = self._binding()
        first, second = NoCompare(), NoCompare()
        item["isVisible"]((first, second))
        item["execute"]((second, first))
        self.assertIs(self.received[0][0], first)
        self.assertIs(self.received[0][1], second)


class HostNameCollisionTests(unittest.TestCase):
    def _action(self, identifier, caption="Name", **kwargs):
        return Action(identifier, caption, lambda selection: None, **kwargs)

    def test_same_context_default_names_conflict(self):
        registry = ActionRegistry()
        first = self._action("first")
        registry.register(first)
        with self.assertRaisesRegex(ValueError, "Duplicate Flame action name"):
            registry.register(self._action("second"))
        self.assertEqual(registry.actions(), (first,))

    def test_explicit_name_conflicts_across_hierarchy_in_same_context(self):
        registry = ActionRegistry()
        first = self._action("first", "Original", flame_name="Stable", hierarchy=())
        registry.register(first)
        with self.assertRaisesRegex(ValueError, "Duplicate Flame action name"):
            registry.register(self._action("second", "Stable", hierarchy=("Other",)))
        self.assertEqual(registry.actions(), (first,))

    def test_batch_collision_against_existing_is_atomic(self):
        registry = ActionRegistry()
        first = self._action("first")
        registry.register(first)
        with self.assertRaisesRegex(ValueError, "Duplicate Flame action name"):
            registry.register_many((self._action("new", "New"), self._action("collision")))
        self.assertEqual(registry.actions(), (first,))

    def test_batch_collision_within_pending_is_atomic(self):
        registry = ActionRegistry()
        with self.assertRaisesRegex(ValueError, "Duplicate Flame action name"):
            registry.register_many((self._action("first"), self._action("second")))
        self.assertEqual(registry.actions(), ())

    def test_overlap_across_multi_context_actions_is_rejected(self):
        registry = ActionRegistry()
        first = self._action("first", contexts=("main_menu", "media_panel"))
        registry.register(first)
        with self.assertRaisesRegex(ValueError, "media_panel"):
            registry.register(self._action("second", contexts=("media_panel", "timeline")))
        self.assertEqual(registry.actions(), (first,))

    def test_disjoint_contexts_and_distinct_explicit_names_remain_valid(self):
        registry = ActionRegistry()
        first = self._action("first", contexts=("main_menu",))
        second = self._action("second", contexts=("media_panel",))
        third = self._action("third", flame_name="Different", contexts=("main_menu",))
        registry.register_many((first, second, third))
        self.assertEqual(registry.actions(), (first, second, third))
        self.assertEqual(registry.actions("main_menu"), (first, third))

    def test_extension_conflict_rejects_whole_extension_and_continues(self):
        registry = ActionRegistry()
        first = self._action("first")
        registry.register(first)

        def bad(staging):
            staging.register_many((self._action("new", "New"), self._action("collision")))

        good = self._action("good", "Good")
        modules = {"bad": SimpleNamespace(register=bad),
                   "good": SimpleNamespace(register=lambda staging: staging.register(good))}
        with patch("dg_python_scripts.extensions.loader.importlib.import_module",
                   side_effect=modules.__getitem__), self.assertLogs("dgpy.extensions", level="ERROR"):
            self.assertEqual(load_extensions(("bad", "good"), registry), ("good",))
        self.assertEqual(registry.actions(), (first, good))


class RegistryMenuAuditTests(unittest.TestCase):
    def test_duplicate_batch_does_not_partially_register(self):
        registry = ActionRegistry()
        existing = Action("existing", "Existing", lambda selection: None)
        registry.register(existing)
        new = Action("new", "New", lambda selection: None)
        with self.assertRaises(ValueError):
            registry.register_many((new, new))
        self.assertEqual(registry.actions(), (existing,))

    def test_failing_registration_iterator_does_not_partially_register(self):
        registry = ActionRegistry()
        def pending():
            yield Action("new", "New", lambda selection: None)
            raise RuntimeError("iterator failed")
        with self.assertRaisesRegex(RuntimeError, "iterator failed"):
            registry.register_many(pending())
        self.assertEqual(registry.actions(), ())

    def test_menu_rebuild_preserves_callbacks_but_copies_dictionaries(self):
        received = []
        registry = ActionRegistry()
        registry.register(Action("menu", "Menu", received.append, contexts=("media_panel",)))
        broker = SelectionBroker()
        first = build_menu(registry, "media_panel", broker=broker)[0]["actions"][0]
        target = SimpleNamespace(selected=False)
        first["isVisible"]((target,))
        first["caption"] = "Changed by caller"
        first["execute"] = lambda selection: self.fail("mutated menu leaked")
        rebuilt = build_menu(registry, "media_panel", broker=broker)[0]["actions"][0]
        self.assertEqual(rebuilt["caption"], "Menu")
        rebuilt["execute"]((object(),))
        self.assertEqual(received, [(target,)])


class HookAuditTests(unittest.TestCase):
    def test_failed_registry_initialization_is_not_published_and_can_retry(self):
        def fail(registry):
            registry.register(Action("partial", "Partial", lambda selection: None))
            raise RuntimeError("initialization failed")
        with patch.object(hooks, "_registry", None), patch.object(
            hooks, "register_builtin_actions", side_effect=fail
        ), patch.object(hooks, "load_extensions") as extensions:
            with self.assertRaisesRegex(RuntimeError, "initialization failed"):
                hooks._get_registry(SimpleNamespace())
            self.assertIsNone(hooks._registry)
            extensions.assert_not_called()
            with patch.object(hooks, "register_builtin_actions"), patch.object(hooks, "load_config") as config:
                config.return_value.extensions.modules = ()
                self.assertEqual(hooks.get_registry().actions(), ())

    def test_all_seven_hooks_delegate_to_their_context(self):
        for context in sorted(ACTION_CONTEXTS):
            with self.subTest(context=context), patch.object(hooks, "_get_custom_ui_actions", return_value=()) as delegate:
                self.assertEqual(getattr(hooks, "get_" + context + "_custom_ui_actions")(), ())
                delegate.assert_called_once_with(context)

    def test_thin_bootstrap_contains_each_delegation_failure(self):
        spec = importlib.util.spec_from_file_location("g2_audit_bootstrap", ROOT / "bootstrap/dgpy_bootstrap.py")
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        for context in sorted(ACTION_CONTEXTS):
            name = "get_" + context + "_custom_ui_actions"
            with self.subTest(context=context), patch.object(hooks, name, side_effect=RuntimeError("unavailable")) as delegate:
                with self.assertLogs("dgpy.bootstrap", level="ERROR"):
                    self.assertEqual(getattr(bootstrap, name)(), ())
                delegate.assert_called_once_with()
