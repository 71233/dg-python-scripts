"""Exercise registry, config and runtime contracts without Flame or Qt."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dgpy.actions.main_menu import build_main_menu
from dgpy.actions.registry import Action, ActionRegistry
from dgpy.config.loader import Config, load_config
from dgpy import hooks
from dgpy.runtime import detect_runtime, parse_version

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_registration_order_and_callback_contract(self):
        registry = ActionRegistry()
        received = []
        registry.register(Action("ext.one", "One", received.append))
        registry.register(Action("ext.two", "Two", received.append))
        group, = build_main_menu(registry)
        self.assertEqual(group["name"], "DGpy")
        self.assertIsInstance(group["actions"], tuple)
        self.assertEqual([a["name"] for a in group["actions"]], ["ext.one", "ext.two"])
        selection = (object(),)
        group["actions"][0]["execute"](selection)
        self.assertEqual(received, [selection])

    def test_duplicate_rejected(self):
        registry = ActionRegistry()
        action = Action("ext.one", "One", lambda selection: None)
        registry.register(action)
        with self.assertRaises(ValueError):
            registry.register(action)
        self.assertEqual(registry.actions(), (action,))

    def test_empty_registry(self):
        self.assertEqual(build_main_menu(ActionRegistry()), ())

    def test_invalid_actions(self):
        for identifier, caption in [("", "One"), ("one", " ")]:
            with self.assertRaises(ValueError):
                Action(identifier, caption, lambda selection: None)
        with self.assertRaises(TypeError):
            Action("one", "One", None)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_config(), Config())

    def test_file_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"menu_caption": "DG Tools"}), encoding="utf-8")
            with patch.dict(os.environ, {"DGPY_CONFIG": str(path)}):
                self.assertEqual(load_config().menu_caption, "DG Tools")
            with patch.dict(os.environ, {"DGPY_CONFIG": "/missing/environment.json"}):
                self.assertEqual(load_config(path).menu_caption, "DG Tools")

    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for value in [[], {"menu_caption": ""}, {"menu_caption": 5}, {"unknown": True}]:
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(ValueError):
                    load_config(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load_config(path)
            with self.assertRaises(FileNotFoundError):
                load_config(Path(directory) / "missing.json")


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
        with patch("dgpy.runtime.importlib.import_module", side_effect=error):
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
            self.assertEqual([a["name"] for a in first[0]["actions"]], ["dgpy.about", "ext.test"])

    def bootstrap(self):
        spec = importlib.util.spec_from_file_location(
            "test_dgpy_bootstrap", ROOT / "bootstrap/dgpy_bootstrap.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_bootstrap_delegates(self):
        with patch("dgpy.hooks.get_main_menu_custom_ui_actions", return_value=("sentinel",)):
            self.assertEqual(self.bootstrap().get_main_menu_custom_ui_actions(), ("sentinel",))

    def test_bootstrap_contains_failures(self):
        with patch("dgpy.hooks.get_main_menu_custom_ui_actions", side_effect=ValueError("bad config")):
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
            "import dgpy, dgpy.hooks, dgpy.ui.about; "
            "assert 'flame' not in sys.modules; assert 'PySide6' not in sys.modules"
        )
        result = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
