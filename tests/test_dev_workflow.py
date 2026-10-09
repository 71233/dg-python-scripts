"""Exercise safety against real temporary Git repositories, never Flame/user files."""
import contextlib
import fcntl
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("dgpy_dev", Path(__file__).parents[1] / "tools/dgpy_dev.py")
DEV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEV)


def run(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class DevWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="DGpy test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.hooks = self.root / "user hooks"
        self.public = self.repo("dg-python-scripts")
        self.internal = self.repo("dg-python-scripts-internal")

    def repo(self, name):
        origin = self.root / (name + ".git")
        seed = self.root / (name + "-seed")
        checkout = self.root / name
        run("git", "init", "--bare", str(origin))
        run("git", "init", "-b", "main", str(seed))
        run("git", "config", "user.email", "test@example.invalid", cwd=seed)
        run("git", "config", "user.name", "Test", cwd=seed)
        (seed / "bootstrap").mkdir()
        (seed / "bootstrap/dgpy_bootstrap.py").write_text("# bootstrap\n")
        (seed / "src").mkdir()
        (seed / "src/module.py").write_text("# source\n")
        (seed / ".gitignore").write_text("*.cache\n")
        run("git", "add", ".", cwd=seed)
        run("git", "commit", "-m", "initial", cwd=seed)
        run("git", "remote", "add", "origin", str(origin), cwd=seed)
        run("git", "push", "-u", "origin", "main", cwd=seed)
        run("git", "clone", "-b", "main", str(origin), str(checkout))
        run("git", "config", "user.email", "test@example.invalid", cwd=checkout)
        run("git", "config", "user.name", "Test", cwd=checkout)
        return checkout

    def cli(self, *args):
        self.output = io.StringIO()
        with contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.output):
            return DEV.main([args[0], "--root", str(self.root), *args[1:]])

    def remote_change(self, repo, branch="main", filename="new.py"):
        seed = self.root / (repo.name + "-seed")
        if branch != "main":
            run("git", "checkout", "-b", branch, cwd=seed)
        (seed / filename).write_text("# new\n")
        run("git", "add", "-f", filename, cwd=seed)
        run("git", "commit", "-m", "remote change", cwd=seed)
        run("git", "push", "origin", branch, cwd=seed)
        return run("git", "rev-parse", "HEAD", cwd=seed)

    def head(self, repo):
        return run("git", "rev-parse", "HEAD", cwd=repo)

    def test_concurrent_helper_is_refused(self):
        with (self.root / ".dgpy-dev.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.cli("update"), 1)
            self.assertIn("Another DGpy", self.output.getvalue())

    def test_special_branch_name_refused(self):
        original = self.head(self.public)
        self.assertEqual(self.cli("switch", "--repo", "public", "@{-1}"), 1)
        self.assertEqual(self.head(self.public), original)

    def test_update_fast_forwards_both(self):
        expected = self.remote_change(self.public)
        self.assertEqual(self.cli("update"), 0)
        self.assertEqual(self.head(self.public), expected)

    def test_second_dirty_repo_blocks_first_before_fetch(self):
        original = self.head(self.public)
        self.remote_change(self.public)
        (self.internal / "untracked").write_text("keep")
        self.assertEqual(self.cli("update"), 1)
        self.assertEqual(self.head(self.public), original)
        self.assertFalse((self.public / "new.py").exists())

    def test_tracked_change_is_preserved(self):
        path = self.public / "src/module.py"
        path.write_text("unsaved")
        self.assertEqual(self.cli("update", "--repo", "public"), 1)
        self.assertEqual(path.read_text(), "unsaved")

    def test_detached_head_refused(self):
        run("git", "checkout", "--detach", cwd=self.public)
        self.assertEqual(self.cli("update", "--repo", "public"), 1)

    def test_git_operation_refused(self):
        (self.public / ".git/rebase-merge").mkdir()
        self.assertEqual(self.cli("update", "--repo", "public"), 1)

    def test_ahead_branch_refused(self):
        (self.public / "local.py").write_text("# local")
        run("git", "add", ".", cwd=self.public)
        run("git", "commit", "-m", "local", cwd=self.public)
        original = self.head(self.public)
        self.assertEqual(self.cli("update", "--repo", "public"), 1)
        self.assertEqual(self.head(self.public), original)

    def test_diverged_branch_refused(self):
        (self.public / "local.py").write_text("# local")
        run("git", "add", ".", cwd=self.public)
        run("git", "commit", "-m", "local", cwd=self.public)
        original = self.head(self.public)
        self.remote_change(self.public)
        self.assertEqual(self.cli("update", "--repo", "public"), 1)
        self.assertEqual(self.head(self.public), original)

    def test_switch_remote_branch_and_existing_branch(self):
        expected = self.remote_change(self.internal, "test/probe")
        self.assertEqual(self.cli("switch", "--repo", "internal", "test/probe"), 0)
        self.assertEqual(self.head(self.internal), expected)
        self.assertEqual(self.cli("switch", "--repo", "internal", "main"), 0)
        self.assertEqual(self.cli("switch", "--repo", "internal", "test/probe"), 0)
        self.assertEqual(run("git", "rev-parse", "--abbrev-ref", "@{upstream}", cwd=self.internal), "origin/test/probe")

    def test_missing_branch_leaves_head(self):
        original = self.head(self.public)
        self.assertEqual(self.cli("switch", "--repo", "public", "missing"), 1)
        self.assertEqual(self.head(self.public), original)

    def test_missing_second_target_blocks_first_switch(self):
        self.remote_change(self.public, "test/probe")
        original = self.head(self.public)
        self.assertEqual(self.cli("switch", "--repo", "all", "test/probe"), 1)
        self.assertEqual(self.head(self.public), original)

    def test_wrong_upstream_refused(self):
        run("git", "config", "branch.main.remote", "elsewhere", cwd=self.public)
        self.assertEqual(self.cli("update", "--repo", "public"), 1)

    def test_local_target_wrong_upstream_refused(self):
        self.remote_change(self.public, "test/probe")
        run("git", "branch", "test/probe", cwd=self.public)
        original = self.head(self.public)
        self.assertEqual(self.cli("switch", "--repo", "public", "test/probe"), 1)
        self.assertEqual(self.head(self.public), original)

    def test_ignored_file_protected(self):
        self.remote_change(self.public, "test/probe", "data.cache")
        path = self.public / "data.cache"
        path.write_text("precious")
        self.assertEqual(self.cli("switch", "--repo", "public", "test/probe"), 1)
        self.assertEqual(path.read_text(), "precious")
        self.assertEqual(run("git", "branch", "--show-current", cwd=self.public), "main")

    def test_setup_preview_apply_idempotent_and_status(self):
        options = ("--hook-dir", str(self.hooks))
        self.assertEqual(self.cli("setup", *options), 0)
        self.assertFalse(self.hooks.exists())
        self.assertEqual(self.cli("setup", *options, "--apply"), 0)
        self.assertEqual(self.cli("setup", *options, "--apply"), 0)
        self.assertTrue((self.hooks / "dgpy_bootstrap.py").is_symlink())
        self.assertEqual(self.cli("status", *options), 0)
        self.assertIn("commit:", self.output.getvalue())

    def test_existing_file_and_foreign_broken_link_protected(self):
        self.hooks.mkdir()
        path = self.hooks / "dgpy_bootstrap.py"
        path.write_text("existing")
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--apply"), 1)
        self.assertEqual(path.read_text(), "existing")
        path.unlink()
        path.symlink_to(self.root / "missing.py")
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--apply"), 1)
        self.assertTrue(path.is_symlink())

    def test_probe_conflict_preflight_leaves_bootstrap_missing(self):
        probe = self.internal / "experiments/dgpy_probe.py"
        probe.parent.mkdir()
        probe.write_text("# probe")
        self.hooks.mkdir()
        (self.hooks / probe.name).write_text("keep")
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--probe", str(probe), "--apply"), 1)
        self.assertFalse((self.hooks / "dgpy_bootstrap.py").exists())

    def test_probe_explicit_only_and_missing_detected(self):
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--probe", str(self.root / "elsewhere.py")), 1)
        probe = self.internal / "experiments/dgpy_probe.py"
        probe.parent.mkdir()
        probe.write_text("# probe")
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--probe", str(probe), "--apply"), 0)
        probe.unlink()
        self.assertEqual(self.cli("status", "--hook-dir", str(self.hooks), "--probe", str(probe)), 1)

    def test_environment_handles_spaces(self):
        self.assertEqual(self.cli("env", "--with-internal"), 0)
        env = self.output.getvalue()
        result = run("/bin/sh", "-c", env + '\nprintf "%s" "$PYTHONPATH"')
        self.assertTrue(result.startswith(str(self.public / "src") + ":" + str(self.internal / "src")))

    def test_install_stable_copy_and_conflict_protection(self):
        directory = self.root / "bin"
        self.assertEqual(self.cli("install", "--bin-dir", str(directory), "--apply"), 0)
        self.assertEqual(self.cli("install", "--bin-dir", str(directory), "--apply"), 0)
        for command in ("dgpy-update", "dgpy-status", "dgpy-switch", "dgpy-setup"):
            self.assertTrue((directory / command).is_symlink())
            result = run(str(directory / command), "--help")
            self.assertIn("usage:", result)
        self.assertIn("PYTHONPATH", run(str(directory / "dgpy-setup"), "env", "--root", str(self.root)))
        (directory / "dgpy").write_text("existing tool")
        self.assertEqual(self.cli("install", "--bin-dir", str(directory), "--apply"), 1)
        self.assertEqual((directory / "dgpy").read_text(), "existing tool")


if __name__ == "__main__":
    unittest.main()
