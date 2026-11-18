"""End-to-end machine setup against disposable local Git origins and hook dirs."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).parents[1]
SCRIPT = SOURCE / "tools" / "dgpy-machine.sh"


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *map(str, args)], cwd=cwd, check=True,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


class MachineSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dgpy machine ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.root = self.home / "DGpy"
        self.hooks = self.home / "user hooks"
        self.remotes = {}
        self.sources = {}
        self.environment = {
            **os.environ, "HOME": str(self.home), "DGPY_PYTHON": sys.executable,
            "DL_PYTHON_HOOK_PATH": "", "DGPY_CONFIG": "",
            "DGPY_ROOT": str(self.root),
        }
        for key, name in (("public", "dg-python-scripts"),
                          ("internal", "dg-python-scripts-internal")):
            origin = self.base / (name + ".git")
            work = self.base / (name + "-source")
            git("init", "--bare", origin)
            git("init", work)
            git("checkout", "-b", "chore/dev-workflow", cwd=work)
            git("config", "user.name", "Fixture", cwd=work)
            git("config", "user.email", "fixture@example.invalid", cwd=work)
            if key == "public":
                (work / "tools").mkdir()
                (work / "bootstrap").mkdir()
                for filename in ("dgpy", "dgpy_dev.py"):
                    shutil.copy2(SOURCE / "tools" / filename,
                                 work / "tools" / filename)
                (work / "bootstrap" / "dgpy_bootstrap.py").write_text(
                    "def get_main_menu_custom_ui_actions(): return ()\n")
            else:
                (work / "examples").mkdir()
                (work / "examples" / "dgpy.toml").write_text(
                    '[extensions]\nmodules = ["dg_python_scripts_internal"]\n')
            git("add", ".", cwd=work)
            git("commit", "-m", "initial fixture", cwd=work)
            git("remote", "add", "origin", origin, cwd=work)
            git("push", "-u", "origin", "chore/dev-workflow", cwd=work)
            git("--git-dir=" + str(origin), "symbolic-ref",
                "HEAD", "refs/heads/chore/dev-workflow")
            self.remotes[key] = origin
            self.sources[key] = work
        self.environment["DGPY_PUBLIC_REMOTE"] = str(self.remotes["public"])
        self.environment["DGPY_INTERNAL_REMOTE"] = str(self.remotes["internal"])

    def invoke(self, *options, success=True):
        args = ["/bin/sh", str(SCRIPT), "--root", str(self.root),
                "--hook-dir", str(self.hooks), *options]
        result = subprocess.run(args, env=self.environment,
                                text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_preview_then_install_repeat_and_update_public(self):
        self.invoke("--public-only")
        self.assertFalse(self.root.exists())
        self.invoke("--public-only", "--apply")
        link = self.hooks / "dgpy_bootstrap.py"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (self.root / "dg-python-scripts"
                         / "bootstrap" / "dgpy_bootstrap.py").resolve())
        current = self.root / "bin-managed"
        old = current.resolve()
        self.assertTrue((current / "dgpy-status").exists())
        self.invoke("--public-only", "--apply")
        self.assertEqual(current.resolve(), old)

        (self.sources["public"] / "README.md").write_text("update\n")
        git("add", ".", cwd=self.sources["public"])
        git("commit", "-m", "fixture update", cwd=self.sources["public"])
        git("push", "origin", "chore/dev-workflow", cwd=self.sources["public"])
        self.invoke("--public-only", "--apply")
        self.assertNotEqual(current.resolve(), old)
        self.assertTrue(old.exists())
        self.assertTrue(link.is_symlink())

        (self.root / "dg-python-scripts" / "untracked").write_text("protect\n")
        before = current.resolve()
        result = self.invoke("--public-only", "--apply", success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dirty", result.stderr)
        self.assertEqual(current.resolve(), before)

    def test_internal_site_config_and_shared_mode(self):
        self.invoke("--with-internal", "--apply")
        config = self.root / "site.toml"
        self.assertTrue(config.is_file())
        config.write_text("# user edited\n")
        current = (self.root / "bin-managed").resolve()
        self.invoke("--with-internal", "--apply")
        self.assertEqual(config.read_text(), "# user edited\n")
        self.assertEqual((self.root / "bin-managed").resolve(), current)

        (self.sources["public"] / "README.md").write_text("next update\n")
        git("add", ".", cwd=self.sources["public"])
        git("commit", "-m", "fixture update", cwd=self.sources["public"])
        git("push", "origin", "chore/dev-workflow", cwd=self.sources["public"])
        old_sha = git("-C", self.root / "dg-python-scripts", "rev-parse", "HEAD")
        self.invoke("--with-internal", "--shared", "--apply")
        self.assertEqual(git("-C", self.root / "dg-python-scripts",
                             "rev-parse", "HEAD"), old_sha)
        self.assertEqual((self.root / "bin-managed").resolve(), current)

    def test_existing_hook_conflict_is_never_replaced(self):
        self.hooks.mkdir()
        protected = self.hooks / "dgpy_bootstrap.py"
        protected.write_text("# already installed\n")
        result = self.invoke("--public-only", "--apply", success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(protected.read_text(), "# already installed\n")


if __name__ == "__main__":
    unittest.main()
