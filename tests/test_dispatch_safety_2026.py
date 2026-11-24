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
from dg_python_scripts.actions.selection import SelectionBroker

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

        item = SelectionBroker().bind(
            Action("visible", "Visible", received.append, is_visible=visible),
            "media_panel",
        )
        self.assertTrue(item["isVisible"]((old,)))
        with self.assertRaisesRegex(ValueError, "injected visibility failure"):
            item["isVisible"]((failed,))
        self._assert_blocked(item, (current,))
        self._assert_blocked(item, (failed,))
        self.assertEqual(received, [])

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

        class UntouchableSelection:
            def __iter__(self):
                raise AssertionError("must not inspect execute input")

        def enabled(selection):
            self._assert_blocked(item, UntouchableSelection())
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
