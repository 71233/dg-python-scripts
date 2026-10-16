"""Exercise safety against real temporary Git repositories, never Flame/user files."""
import contextlib
import fcntl
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
        hook_environment = mock.patch.dict(os.environ, {"DL_PYTHON_HOOK_PATH": "", "DGPY_CONFIG": "", "DGPY_FLAME_EXECUTABLE": ""})
        hook_environment.start()
        self.addCleanup(hook_environment.stop)
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

    def test_same_commit_branch_change_during_preflight_is_refused(self):
        original = self.head(self.public)
        self.remote_change(self.public)
        real_git = DEV.git

        def external_switch(repo, *args, **kwargs):
            result = real_git(repo, *args, **kwargs)
            if repo == self.internal and args[:1] == ("fetch",):
                run("git", "checkout", "-b", "external", cwd=self.public)
            return result

        with mock.patch.object(DEV, "git", side_effect=external_switch):
            self.assertEqual(self.cli("update"), 1)
        self.assertEqual(self.head(self.public), original)
        self.assertEqual(run("git", "branch", "--show-current", cwd=self.public), "external")

    def test_ref_change_during_preflight_is_refused(self):
        original = self.head(self.public)
        self.remote_change(self.public)
        real_git = DEV.git

        def external_fetch(repo, *args, **kwargs):
            result = real_git(repo, *args, **kwargs)
            if repo == self.internal and args[:1] == ("fetch",):
                run("git", "update-ref", "refs/remotes/origin/main", original, cwd=self.public)
            return result

        with mock.patch.object(DEV, "git", side_effect=external_fetch):
            self.assertEqual(self.cli("update"), 1)
        self.assertEqual(self.head(self.public), original)

    def test_second_repo_dirtied_after_plan_blocks_first_update(self):
        original = self.head(self.public)
        self.remote_change(self.public)
        real_git = DEV.git

        def external_edit(repo, *args, **kwargs):
            result = real_git(repo, *args, **kwargs)
            if repo == self.internal and args == ("rev-parse", "HEAD"):
                (self.internal / "untracked").write_text("keep")
            return result

        with mock.patch.object(DEV, "git", side_effect=external_edit):
            self.assertEqual(self.cli("update"), 1)
        self.assertEqual(self.head(self.public), original)
        self.assertEqual((self.internal / "untracked").read_text(), "keep")

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

    def test_duplicate_copy_in_additional_root_blocks_setup(self):
        other = self.root / "project hooks"
        other.mkdir()
        copy = other / "dgpy_bootstrap.py"
        copy.write_text("existing hook")
        options = ("--hook-dir", str(self.hooks), "--check-hook-dir", str(other))
        self.assertEqual(self.cli("setup", *options, "--apply"), 1)
        self.assertFalse(self.hooks.exists())
        self.assertEqual(copy.read_text(), "existing hook")
        self.assertEqual(self.cli("status", *options), 1)
        self.assertIn("DUPLICATE CANDIDATE", self.output.getvalue())

    def test_duplicate_link_with_other_name_blocks_setup(self):
        self.hooks.mkdir()
        alias = self.hooks / "old_bootstrap.py"
        alias.symlink_to(self.public / "bootstrap/dgpy_bootstrap.py")
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--apply"), 1)
        self.assertTrue(alias.is_symlink())
        self.assertFalse((self.hooks / "dgpy_bootstrap.py").exists())

    def test_environment_hook_root_and_nested_duplicate_are_scanned(self):
        other = self.root / "shared hooks"
        nested = other / "nested"
        nested.mkdir(parents=True)
        (nested / "dgpy_bootstrap.py").write_text("existing hook")
        with mock.patch.dict(os.environ, {"DL_PYTHON_HOOK_PATH": str(other)}):
            self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--apply"), 1)
        self.assertFalse(self.hooks.exists())

    def test_unrelated_hook_does_not_block_setup(self):
        self.hooks.mkdir()
        path = self.hooks / "other_tool.py"
        path.write_text("existing unrelated hook")
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--apply"), 0)
        self.assertEqual(path.read_text(), "existing unrelated hook")

    def test_default_hook_paths_for_mac_and_linux(self):
        for system, suffix in (("Darwin", "Library/Preferences/Autodesk/flame/python"),
                               ("Linux", "flame/python")):
            with mock.patch.object(DEV.platform, "system", return_value=system):
                with mock.patch.object(DEV.Path, "home", return_value=self.root):
                    self.assertEqual(self.cli("setup", "--apply"), 0)
                    self.assertTrue((self.root / suffix / "dgpy_bootstrap.py").is_symlink())

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

    def launcher(self, version="2025.2.7"):
        product = self.root / "flame_2025.2.7"
        (product / "bin").mkdir(parents=True, exist_ok=True)
        (product / "VERSION").write_text('#define VERSION "' + version + '"\n')
        executable = product / "bin/startApplication"
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
        self.assertEqual(self.cli("setup", "--hook-dir", str(self.hooks), "--apply"), 0)
        return executable

    def flame_cli(self, executable, *options):
        return self.cli("flame", "--flame-executable", str(executable),
                        "--hook-dir", str(self.hooks), *options)

    def test_flame_preview_never_executes_or_changes_environment(self):
        executable = self.launcher()
        before = dict(os.environ)
        with mock.patch.object(DEV.os, "execve") as execute:
            self.assertEqual(self.flame_cli(executable, "--dry-run"), 0)
            execute.assert_not_called()
        self.assertEqual(dict(os.environ), before)

    def test_flame_exec_child_environment_and_loaded_user_preserved(self):
        executable = self.launcher()
        with mock.patch.dict(os.environ, {"PYTHONPATH": "existing packages", "HOME": str(self.root),
                                         "DL_PYTHON_HOOK_PATH": "", "DGPY_CONFIG": ""}):
            before = dict(os.environ)
            with mock.patch.object(DEV.os, "execve") as execute:
                self.assertEqual(self.flame_cli(executable), 0)
            command, argv, child = execute.call_args.args
            self.assertEqual(command, str(executable))
            self.assertEqual(argv, [str(executable)])
            self.assertEqual(child["PYTHONPATH"], str(self.public / "src") + ":existing packages")
            self.assertNotIn("DGPY_CONFIG", child)
            for key in ("HOME", "DL_PYTHON_HOOK_PATH"):
                self.assertEqual(child[key], before[key])
            self.assertEqual(dict(os.environ), before)

    def test_flame_wrong_version_missing_hook_or_duplicate_stops_before_exec(self):
        executable = self.launcher("2026.2.3")
        with mock.patch.object(DEV.os, "execve") as execute:
            self.assertEqual(self.flame_cli(executable), 1)
            executable = self.launcher()
            (self.hooks / "dgpy_bootstrap.py").unlink()
            self.assertEqual(self.flame_cli(executable), 1)
            self.launcher()
            (self.hooks / "alias.py").symlink_to(self.public / "bootstrap/dgpy_bootstrap.py")
            self.assertEqual(self.flame_cli(executable), 1)
            execute.assert_not_called()

    def test_flame_unrelated_legacy_hook_is_preserved(self):
        executable = self.launcher()
        legacy = self.hooks / "legacy.py"
        legacy.write_text("# unrelated existing hook")
        self.assertEqual(self.flame_cli(executable, "--dry-run"), 0)
        self.assertEqual(legacy.read_text(), "# unrelated existing hook")

    def test_flame_internal_requires_config_and_rejects_bad_toml(self):
        executable = self.launcher()
        with mock.patch.dict(os.environ, {"DGPY_CONFIG": ""}), mock.patch.object(DEV.os, "execve") as execute:
            self.assertEqual(self.flame_cli(executable, "--with-internal"), 1)
            config = self.root / "broken.toml"
            config.write_text("[broken")
            self.assertEqual(self.flame_cli(executable, "--config", str(config)), 1)
            execute.assert_not_called()

    def test_flame_vendor_defaults_and_explicit_path(self):
        executable = self.launcher()
        args = mock.Mock(flame_executable=executable)
        self.assertEqual(DEV.flame_executable(args), executable)
        for system, expected in (("Darwin", "/opt/Autodesk/flame_2025.2.7/bin/startApplication"),
                                  ("Linux", "/opt/Autodesk/.flamefamily_2025.2.7/bin/startApplication")):
            args.flame_executable = None
            with mock.patch.dict(os.environ, {"DGPY_FLAME_EXECUTABLE": ""}), \
                    mock.patch.object(DEV.platform, "system", return_value=system), \
                    mock.patch.object(DEV.Path, "is_file", return_value=True), \
                    mock.patch.object(DEV.os, "access", return_value=True), \
                    mock.patch.object(DEV.Path, "read_text", return_value='#define VERSION "2025.2.7"\n'):
                self.assertEqual(str(DEV.flame_executable(args)), expected)

    @unittest.skipIf(sys.version_info < (3, 11), "TOML requires Python 3.11")
    def test_flame_inherited_config_validates_schema_and_passes_internal_paths(self):
        executable = self.launcher()
        # Use the real config schema without introducing a dependency on Core.
        package = self.public / "src/dg_python_scripts"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "config.py").write_bytes((Path(__file__).parents[1] / "src/dg_python_scripts/config/loader.py").read_bytes())
        config = self.root / "site config.toml"
        config.write_text('[extensions]\nmodules = ["example_extension"]\n')
        with mock.patch.dict(os.environ, {"DGPY_CONFIG": str(config)}), mock.patch.object(DEV.os, "execve") as execute:
            self.assertEqual(self.flame_cli(executable, "--with-internal"), 0, self.output.getvalue())
            child = execute.call_args.args[2]
            self.assertEqual(child["DGPY_CONFIG"], str(config))
            self.assertTrue(child["PYTHONPATH"].startswith(str(self.public / "src") + ":" + str(self.internal / "src")))
            self.assertEqual(child["START_APPLICATION_FLAVOUR"], "flame")
            execute.reset_mock()
            config.write_text("unknown_key = true\n")
            self.assertEqual(self.flame_cli(executable), 1)
            execute.assert_not_called()


class ShellRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="DGpy runtime ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "stable bin"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(DEV.main(["install", "--bin-dir", str(self.bin), "--apply"]), 0)
        self.env = dict(os.environ, DGPY_PYTHON=sys.executable)

    def call(self, command, *args, env=None):
        return subprocess.run([str(self.bin / command), *args], env=env or self.env,
                              text=True, capture_output=True)

    def test_all_commands_use_selected_runtime_with_spaces_and_ignore_pythonpath(self):
        poison = self.root / "poison"
        poison.mkdir()
        (poison / "argparse.py").write_text("raise RuntimeError('inherited Python path used')")
        runtime = self.root / "chosen Python"
        runtime.symlink_to(sys.executable)
        env = dict(self.env, DGPY_PYTHON=str(runtime), PYTHONPATH=str(poison))
        for command in ("dgpy-status", "dgpy-update", "dgpy-switch", "dgpy-setup", "dgpy-flame"):
            result = self.call(command, "--help", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout)

    def test_invalid_override_fails_closed(self):
        for value in ("relative/python", str(self.root / "missing")):
            result = self.call("dgpy-status", "--help", env=dict(self.env, DGPY_PYTHON=value))
            self.assertEqual(result.returncode, 1)
            self.assertIn("STOP:", result.stderr)
            self.assertNotIn("SyntaxError", result.stderr)

    def test_old_python_is_rejected_before_helper_parse(self):
        old = self.root / "old Python"
        old.write_text("#!/bin/sh\nexit 1\n")
        old.chmod(0o755)
        result = self.call("dgpy-status", "--help", env=dict(self.env, DGPY_PYTHON=str(old)))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Python 3.9+ required", result.stderr)

    def test_bundled_python_precedes_os_python(self):
        bundled = Path("/opt/Autodesk/python/2025.2.7/bin/python3")
        if not bundled.is_file():
            self.skipTest("Bundled Flame Python unavailable; verified on host/container")
        old_bin = self.root / "old bin"
        old_bin.mkdir()
        old = old_bin / "python3"
        old.write_text("#!/bin/sh\necho 'OS Python unexpectedly selected' >&2\nexit 36\n")
        old.chmod(0o755)
        env = dict(self.env, PATH=str(old_bin) + os.pathsep + self.env["PATH"])
        env.pop("DGPY_PYTHON", None)
        result = self.call("dgpy-status", "--help", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_install_is_independent_of_checkout_tools(self):
        for command in ("dgpy-status", "dgpy-update", "dgpy-switch", "dgpy-setup", "dgpy-flame"):
            self.assertEqual(self.call(command, "--help").returncode, 0)
        self.assertFalse((self.root / "dg-python-scripts/tools").exists())

    def test_installed_setup_and_status_run_with_selected_interpreter(self):
        repo = self.root / "dg-python-scripts"
        repo.mkdir()
        run("git", "init", "-b", "main", str(repo))
        run("git", "config", "user.email", "test@example.invalid", cwd=repo)
        run("git", "config", "user.name", "Test", cwd=repo)
        (repo / "bootstrap").mkdir()
        (repo / "bootstrap/dgpy_bootstrap.py").write_text("# test hook\n")
        run("git", "add", ".", cwd=repo)
        run("git", "commit", "-m", "fixture", cwd=repo)
        env = dict(self.env, DGPY_ROOT=str(self.root), DL_PYTHON_HOOK_PATH="")
        if Path("/opt/Autodesk/python/2025.2.7/bin/python3").is_file():
            env.pop("DGPY_PYTHON", None)
        hooks = self.root / "hooks"
        result = self.call("dgpy-setup", "--hook-dir", str(hooks), "--apply", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.call("dgpy-status", "--repo", "public", "--hook-dir", str(hooks), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Python:", result.stdout)
        self.assertNotIn("(3.6.", result.stdout)
        self.assertIn("tree: clean", result.stdout)
        print(result.stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
