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
