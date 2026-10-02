"""Exercise registry, config and runtime contracts without Flame or Qt."""

import importlib.util
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from dg_python_scripts.actions.menu import build_menu
from dg_python_scripts.actions.registry import ACTION_CONTEXTS, Action, ActionRegistry
from dg_python_scripts.actions.selection import SelectionBroker
from dg_python_scripts.config.loader import Config, ExtensionsConfig, UIConfig, load_config
from dg_python_scripts.extensions.loader import load_extensions
from dg_python_scripts import hooks
from dg_python_scripts.runtime import detect_runtime, parse_version
from dg_python_scripts.rename import (
    RenameApplyError,
    apply_plan,
    build_plan,
)

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_registration_order_and_callback_contract(self):
        registry = ActionRegistry()
        received = []
        registry.register(Action("ext.one", "One", received.append))
        registry.register(Action("ext.two", "Two", received.append))
        group, = build_menu(registry, "main_menu")
        self.assertEqual(group["name"], "DGpy")
        self.assertIsInstance(group["actions"], tuple)
        self.assertEqual([a["name"] for a in group["actions"]], ["One", "Two"])
        selection = (object(),)
        group["actions"][0]["execute"](selection)
        self.assertEqual(received, [selection])

    def test_internal_id_is_separate_from_flame_name(self):
        action = Action("dgpy.test", "Readable Label", lambda selection: None)
        item = action.as_menu_item()
        self.assertEqual(action.id, "dgpy.test")
        self.assertEqual(action.host_name, "Readable Label")
        self.assertEqual(item["name"], "Readable Label")
        self.assertEqual(item["caption"], "Readable Label")
        self.assertNotIn("dgpy.test", item.values())

        pinned = Action(
            "dgpy.pinned",
            "New Caption",
            lambda selection: None,
            flame_name="Stable Flame Name",
        )
        self.assertEqual(pinned.host_name, "Stable Flame Name")
        self.assertEqual(pinned.as_menu_item()["name"], "Stable Flame Name")
        self.assertEqual(pinned.as_menu_item()["caption"], "New Caption")

    def test_context_filtering_and_serialization(self):
        registry = ActionRegistry()
        action = Action(
            "ext.multi",
            "Multi",
            lambda selection: None,
            contexts=("main_menu", "media_panel", "main_menu"),
            order=42,
            minimum_version="2025.2.7",
        )
        registry.register(action)

        self.assertEqual(action.contexts, ("main_menu", "media_panel"))
        self.assertEqual(registry.actions("main_menu"), (action,))
        self.assertEqual(registry.actions("media_panel"), (action,))
        self.assertEqual(registry.actions("timeline"), ())

        item = build_menu(registry, "media_panel")[0]["actions"][0]
        self.assertEqual(item["order"], 42)
        self.assertEqual(item["minimumVersion"], "2025.2.7")

    def test_supported_contexts_are_explicit(self):
        self.assertEqual(
            ACTION_CONTEXTS,
            {
                "main_menu",
                "media_panel",
                "mediahub_files",
                "mediahub_archives",
                "timeline",
                "batch",
                "action",
            },
        )
        with self.assertRaises(ValueError):
            Action("bad", "Bad", lambda selection: None, contexts=("unknown",))
        with self.assertRaises(ValueError):
            build_menu(ActionRegistry(), "unknown")

    def test_register_many_is_atomic(self):
        registry = ActionRegistry()
        existing = Action("ext.existing", "Existing", lambda selection: None)
        registry.register(existing)

        new = Action("ext.new", "New", lambda selection: None)
        conflicting = Action("ext.existing", "Conflict", lambda selection: None)
        with self.assertRaises(ValueError):
            registry.register_many((new, conflicting))

        self.assertEqual(registry.actions(), (existing,))

    def test_duplicate_rejected(self):
        registry = ActionRegistry()
        action = Action("ext.one", "One", lambda selection: None)
        registry.register(action)
        with self.assertRaises(ValueError):
            registry.register(action)
        self.assertEqual(registry.actions(), (action,))

    def test_empty_registry(self):
        self.assertEqual(build_menu(ActionRegistry(), "main_menu"), ())

    def test_invalid_actions(self):
        for identifier, caption in [("", "One"), ("one", " ")]:
            with self.assertRaises(ValueError):
                Action(identifier, caption, lambda selection: None)
        with self.assertRaises(TypeError):
            Action("one", "One", None)
        with self.assertRaises(ValueError):
            Action("one", "One", lambda selection: None, flame_name=" ")


class RepositoryBoundaryTests(unittest.TestCase):
    def test_public_source_does_not_reference_internal_package(self):
        for path in (ROOT / "src").rglob("*.py"):
            with self.subTest(path=path):
                self.assertNotIn(
                    "dg_python_scripts_internal",
                    path.read_text(encoding="utf-8"),
                )


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_config(), Config())

    def test_file_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dgpy.toml"
            path.write_text(
                """
[ui]
menu_caption = "DG Tools"

[extensions]
modules = ["ext.one", "ext.two"]
""".strip(),
                encoding="utf-8",
            )
            expected = Config(
                ui=UIConfig(menu_caption="DG Tools"),
                extensions=ExtensionsConfig(modules=("ext.one", "ext.two")),
            )
            with patch.dict(os.environ, {"DGPY_CONFIG": str(path)}):
                self.assertEqual(load_config(), expected)
            with patch.dict(os.environ, {"DGPY_CONFIG": "/missing/environment.toml"}):
                self.assertEqual(load_config(path), expected)

    def test_invalid_config(self):
        invalid_values = (
            'menu_caption = "old-style"',
            '[ui]\nmenu_caption = ""',
            '[ui]\nmenu_caption = 5',
            '[ui]\nunknown = true',
            '[extensions]\nmodules = "not-an-array"',
            '[extensions]\nmodules = ["bad-name"]',
            '[extensions]\nmodules = ["ext.one", "ext.one"]',
            '[unknown]\nenabled = true',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dgpy.toml"
            for value in invalid_values:
                path.write_text(value, encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(ValueError):
                    load_config(path)

            path.write_text("[ui", encoding="utf-8")
            with self.assertRaises(tomllib.TOMLDecodeError):
                load_config(path)
            with self.assertRaises(FileNotFoundError):
                load_config(Path(directory) / "missing.toml")



class ExtensionTests(unittest.TestCase):
    def extension_module(self, name, register=None):
        module = ModuleType(name)
        if register is not None:
            module.register = register
        return module

    def test_configured_extension_registers_once_per_registry(self):
        calls = []

        def register(registry):
            calls.append("called")
            registry.register(
                Action(
                    "dgpy.test.extension",
                    "Extension",
                    lambda selection: None,
                    contexts=("media_panel",),
                )
            )

        module = self.extension_module("test_dgpy_extension", register)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dgpy.toml"
            path.write_text(
                '[extensions]\nmodules = ["test_dgpy_extension"]',
                encoding="utf-8",
            )
            with (
                patch.dict(sys.modules, {"test_dgpy_extension": module}),
                patch.dict(os.environ, {"DGPY_CONFIG": str(path)}, clear=True),
                patch.object(hooks, "_registry", None),
            ):
                names = [
                    action["name"]
                    for action in hooks.get_media_panel_custom_ui_actions()[0]["actions"]
                ]
                self.assertEqual(names, ["Rename...", "Extension"])
                hooks.get_timeline_custom_ui_actions()
                hooks.get_main_menu_custom_ui_actions()

        self.assertEqual(calls, ["called"])

    def test_extension_failures_are_isolated_and_atomic(self):
        def bad_register(registry):
            registry.register(
                Action(
                    "dgpy.test.partial",
                    "Partial",
                    lambda selection: None,
                    contexts=("media_panel",),
                )
            )
            raise RuntimeError("broken extension")

        def good_register(registry):
            registry.register(
                Action(
                    "dgpy.test.good",
                    "Good",
                    lambda selection: None,
                    contexts=("media_panel",),
                )
            )

        modules = {
            "test_bad_extension": self.extension_module("test_bad_extension", bad_register),
            "test_missing_register": self.extension_module("test_missing_register"),
            "test_good_extension": self.extension_module("test_good_extension", good_register),
        }
        registry = ActionRegistry()
        with patch.dict(sys.modules, modules), self.assertLogs("dgpy.extensions", level="ERROR"):
            loaded = load_extensions(
                (
                    "test_bad_extension",
                    "test_missing_register",
                    "test_good_extension",
                ),
                registry,
            )

        self.assertEqual(loaded, ("test_good_extension",))
        self.assertEqual(
            tuple(action.id for action in registry.actions()),
            ("dgpy.test.good",),
        )

class RuntimeTests(unittest.TestCase):
    def test_version_parsing(self):
        for value, expected in [
            ("2025.2.7", (2025, 2, 7)),
            ("Flame 2025.2.7 (build 1234)", (2025, 2, 7)),
            ("2026.1", (2026, 1, 0)),
            ("unknown", None),
        ]:
            with self.subTest(value=value):
                self.assertEqual(parse_version(value), expected)

    def test_runtime_status(self):
        for value, expected in [("2025.2.7", "primary"), ("2026.1", "unvalidated"),
                                ("unknown", "unvalidated"), ("2024.2", "unvalidated")]:
            with patch.dict(sys.modules, {"flame": SimpleNamespace(get_version=lambda: value)}):
                runtime = detect_runtime()
            self.assertEqual(runtime.status, expected)
            self.assertEqual(runtime.flame_version, value)

    def test_outside_flame(self):
        with patch.dict(sys.modules, {"flame": None}):
            self.assertEqual(detect_runtime().status, "outside-flame")

    def test_broken_host_dependency_not_hidden(self):
        error = ModuleNotFoundError("host dependency missing", name="host_dependency")
        with patch("dg_python_scripts.runtime.importlib.import_module", side_effect=error):
            with self.assertRaises(ModuleNotFoundError):
                detect_runtime()


class HookTests(unittest.TestCase):
    def test_builtin_once_and_extension_visible(self):
        with patch.object(hooks, "_registry", None), patch.dict(os.environ, {}, clear=True):
            registry = hooks.get_registry()
            registry.register(Action("ext.test", "Extension", lambda selection: None))
            first = hooks.get_main_menu_custom_ui_actions()
            second = hooks.get_main_menu_custom_ui_actions()
            self.assertEqual(first, second)
            self.assertEqual(
                [a["name"] for a in first[0]["actions"]],
                ["Rename...", "About / Diagnostics", "Extension"],
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_media_panel_custom_ui_actions()[0]["actions"]],
                ["Rename..."],
            )
            for hook in (
                hooks.get_mediahub_files_custom_ui_actions,
                hooks.get_mediahub_archives_custom_ui_actions,
                hooks.get_timeline_custom_ui_actions,
                hooks.get_batch_custom_ui_actions,
                hooks.get_action_custom_ui_actions,
            ):
                self.assertEqual(
                    [action["name"] for action in hook()[0]["actions"]],
                    ["Rename..."],
                )

    def test_multi_context_extension_reaches_only_target_hooks(self):
        with patch.object(hooks, "_registry", None), patch.dict(os.environ, {}, clear=True):
            hooks.get_registry().register(
                Action(
                    "ext.multi",
                    "Multi",
                    lambda selection: None,
                    contexts=("media_panel", "timeline"),
                )
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_main_menu_custom_ui_actions()[0]["actions"]],
                ["Rename...", "About / Diagnostics"],
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_media_panel_custom_ui_actions()[0]["actions"]],
                ["Rename...", "Multi"],
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_timeline_custom_ui_actions()[0]["actions"]],
                ["Rename...", "Multi"],
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_mediahub_files_custom_ui_actions()[0]["actions"]],
                ["Rename..."],
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_mediahub_archives_custom_ui_actions()[0]["actions"]],
                ["Rename..."],
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_batch_custom_ui_actions()[0]["actions"]],
                ["Rename..."],
            )
            self.assertEqual(
                [action["name"] for action in hooks.get_action_custom_ui_actions()[0]["actions"]],
                ["Rename..."],
            )

    def bootstrap(self):
        spec = importlib.util.spec_from_file_location(
            "test_dgpy_bootstrap", ROOT / "bootstrap/dgpy_bootstrap.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_bootstrap_delegates(self):
        bootstrap = self.bootstrap()
        hook_names = (
            "get_main_menu_custom_ui_actions",
            "get_media_panel_custom_ui_actions",
            "get_mediahub_files_custom_ui_actions",
            "get_mediahub_archives_custom_ui_actions",
            "get_timeline_custom_ui_actions",
            "get_batch_custom_ui_actions",
            "get_action_custom_ui_actions",
        )
        for hook_name in hook_names:
            with self.subTest(hook_name=hook_name), patch(
                f"dg_python_scripts.hooks.{hook_name}", return_value=("sentinel",)
            ):
                self.assertEqual(getattr(bootstrap, hook_name)(), ("sentinel",))

    def test_bootstrap_contains_failures(self):
        with patch("dg_python_scripts.hooks.get_main_menu_custom_ui_actions", side_effect=ValueError("bad config")):
            with self.assertLogs("dgpy.bootstrap", level="ERROR") as captured:
                self.assertEqual(self.bootstrap().get_main_menu_custom_ui_actions(), ())
            self.assertIn("bad config", captured.output[0])

    def test_missing_package_in_isolated_process(self):
        code = (
            "import runpy; "
            f"hook = runpy.run_path({str(ROOT / 'bootstrap/dgpy_bootstrap.py')!r}); "
            "assert hook['get_main_menu_custom_ui_actions']() == ()"
        )
        result = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ModuleNotFoundError", result.stderr)

    def test_core_imports_without_host_or_qt(self):
        code = (
            f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
            "import dg_python_scripts, dg_python_scripts.hooks, dg_python_scripts.ui.about; "
            "assert 'flame' not in sys.modules; assert 'PySide6' not in sys.modules"
        )
        result = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)



class FakeNameAttribute:
    def __init__(self, value):
        self.value = value

    def get_value(self):
        return self.value

    def set_value(self, value):
        self.value = value
        return True


class FakeObject:
    def __init__(self, name, selected=True):
        self.name = FakeNameAttribute(name)
        self.selected = selected


class PyBatchIteration(FakeObject):
    pass


class UniqueNameAttribute:
    def __init__(self, owner, namespace, value):
        self.owner = owner
        self.namespace = namespace
        self.value = value

    def get_value(self):
        return self.value

    def set_value(self, value):
        if any(
            other is not self.owner and other.name.get_value() == value
            for other in self.namespace
        ):
            raise RuntimeError("duplicate")
        self.value = value
        return True


class UniqueObject:
    def __init__(self, name, namespace):
        self.selected = True
        self.name = UniqueNameAttribute(self, namespace, name)
        namespace.append(self)


class StickyNameAttribute(FakeNameAttribute):
    def set_value(self, value):
        return True


class StickyObject:
    def __init__(self, name):
        self.name = StickyNameAttribute(name)
        self.selected = True


class SelectionBrokerTests(unittest.TestCase):
    def test_unselected_predicate_target_wins_over_execute_selection(self):
        received = []
        action = Action("test.context", "Context", received.append)
        broker = SelectionBroker()
        item = broker.bind(action, "media_panel")

        reel = FakeObject("Reel", selected=False)
        clip = FakeObject("Clip", selected=True)
        self.assertTrue(item["isVisible"]((reel,)))
        item["execute"]((clip,))

        self.assertEqual(received, [(reel,)])

    def test_selected_stale_predicate_falls_back_to_execute_selection(self):
        received = []
        action = Action("test.shortcut", "Shortcut", received.append)
        broker = SelectionBroker()
        item = broker.bind(action, "media_panel")

        first = FakeObject("A", selected=True)
        second = FakeObject("B", selected=True)
        item["isVisible"]((first,))
        first.selected = False
        item["execute"]((second,))

        self.assertEqual(received, [(second,)])

    def test_same_members_preserve_predicate_order(self):
        received = []
        action = Action("test.order", "Order", received.append)
        broker = SelectionBroker()
        item = broker.bind(action, "media_panel")

        first = FakeObject("A")
        second = FakeObject("B")
        item["isVisible"]((first, second))
        item["execute"]((second, first))

        self.assertEqual(received, [(first, second)])


class RenameTests(unittest.TestCase):
    def test_tokens_and_replace_pipeline(self):
        objects = [FakeObject("A"), FakeObject("B")]
        plan = build_plan(
            objects,
            "{name}_{date:%Y%m%d}_{index:###@8-2}_foo",
            find="foo",
            replace="bar",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

        self.assertEqual(
            [row.new_name for row in plan.rows],
            ["A_20261002_008_bar", "B_20261002_006_bar"],
        )
        self.assertEqual([row.status for row in plan.rows], ["ready", "ready"])

    def test_unsupported_items_do_not_consume_index(self):
        unsupported = SimpleNamespace(name=None, selected=True)
        plan = build_plan(
            (unsupported, FakeObject("A")),
            "{index:###}",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(plan.rows[0].status, "unsupported")
        self.assertEqual(plan.rows[1].new_name, "001")

    def test_batch_iteration_is_known_unsupported(self):
        plan = build_plan(
            (PyBatchIteration("Iteration"),),
            "{name}_x",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(plan.rows[0].status, "unsupported")

    def test_swap_succeeds_in_unique_namespace_via_temporary_phase(self):
        namespace = []
        first = UniqueObject("2", namespace)
        second = UniqueObject("1", namespace)
        plan = build_plan(
            (first, second),
            "{index}",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

        result = apply_plan(plan)

        self.assertEqual(result.changed, 2)
        self.assertEqual(first.name.get_value(), "1")
        self.assertEqual(second.name.get_value(), "2")

    def test_readback_mismatch_is_failure(self):
        obj = StickyObject("A")
        plan = build_plan(
            (obj,),
            "B",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

        with self.assertRaises(RenameApplyError):
            apply_plan(plan)

        self.assertEqual(obj.name.get_value(), "A")


if __name__ == "__main__":
    unittest.main()
