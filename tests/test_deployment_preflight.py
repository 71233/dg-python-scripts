"""Disposable-tree tests for the no-apply Flame Hook placement preflight."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dg_python_scripts.deployment import Evidence, HookRoot, assess_bootstrap


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix="dgpy-hook-test-")
        self.addCleanup(self.sandbox.cleanup)
        self.base = Path(self.sandbox.name)
        self.source = self.base / "checkout" / "bootstrap" / "dgpy_bootstrap.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("def get_main_menu_custom_ui_actions(): return ()\n")
        self.dirs = {}
        for scope in ("user", "project", "application", "shared"):
            directory = self.base / scope
            directory.mkdir()
            self.dirs[scope] = directory
        self.roots = tuple(HookRoot(key, path) for key, path in self.dirs.items())
        self.evidence = Evidence(
            flame_version="2026.2.3",
            roots_confirmed=True,
            additional_paths_confirmed=True,
            security_reviewed=True,
            source_provenance_reviewed=True,
        )

    def report(self, *, roots=None, source=None, evidence=None, target_scope="user"):
        return assess_bootstrap(
            source=self.source if source is None else source,
            roots=self.roots if roots is None else roots,
            target_scope=target_scope,
            evidence=self.evidence if evidence is None else evidence,
        )

    def codes(self, **kwargs):
        return {finding.code for finding in self.report(**kwargs).findings}

    def test_clean_fixture_only_produces_preview_not_apply(self):
        report = self.report()
        self.assertEqual(report.findings, ())
        self.assertEqual(report.inspected_roots, 4)
        self.assertEqual(report.status, "PREVIEW_ONLY")
        self.assertFalse(hasattr(report, "apply"))
        self.assertFalse((self.dirs["user"] / self.source.name).exists())

    def test_unknown_attestations_fail_closed(self):
        report = self.report(evidence=Evidence())
        self.assertEqual(report.status, "BLOCKED")
        self.assertTrue({
            "unvalidated_flame_version",
            "effective_roots_unconfirmed",
            "additional_paths_unconfirmed",
            "ownership_acl_mount_unreviewed",
            "source_revision_unreviewed",
        }.issubset({f.code for f in report.findings}))

    def test_wrong_flame_version_blocks_even_with_known_roots(self):
        evidence = Evidence("2025.2.7", True, True, True, True)
        self.assertIn("unvalidated_flame_version", self.codes(evidence=evidence))

    def test_only_user_or_shared_can_be_target(self):
        self.assertIn("unsupported_target_scope", self.codes(target_scope="application"))
        self.assertEqual(self.report(target_scope="shared").status, "PREVIEW_ONLY")

    def test_unknown_root_blocks(self):
        roots = tuple(HookRoot(r.scope, None if r.scope == "project" else r.path) for r in self.roots)
        self.assertIn("unknown_or_invalid_root", self.codes(roots=roots))

    def test_missing_scope_blocks(self):
        roots = tuple(r for r in self.roots if r.scope != "project")
        self.assertIn("missing_scope", self.codes(roots=roots))

    def test_duplicate_scope_blocks(self):
        self.assertIn("duplicate_scope", self.codes(roots=(*self.roots, self.roots[0])))

    def test_missing_non_target_project_directory_is_allowed(self):
        self.dirs["project"].rmdir()
        self.assertEqual(self.report().status, "PREVIEW_ONLY")
        self.assertEqual(self.report().inspected_roots, 3)

    def test_missing_target_directory_blocks_without_creating(self):
        self.dirs["user"].rmdir()
        self.assertIn("target_root_missing", self.codes())
        self.assertFalse(self.dirs["user"].exists())

    def test_destination_exists_is_always_a_conflict(self):
        destination = self.dirs["user"] / "dgpy_bootstrap.py"
        destination.write_text("already managed?\n")
        self.assertIn("dgpy_candidate_present", self.codes())
        self.assertEqual(destination.read_text(), "already managed?\n")

    def test_alternate_scope_bootstrap_blocks(self):
        (self.dirs["shared"] / "dgpy_bootstrap.py").write_text("existing\n")
        self.assertIn("dgpy_candidate_present", self.codes())

    def test_duplicate_non_dgpy_hook_names_block(self):
        (self.dirs["application"] / "custom_actions.py").write_text("# A\n")
        (self.dirs["project"] / "custom_actions.py").write_text("# B\n")
        self.assertIn("duplicate_hook_basename", self.codes())

    def test_casefolded_duplicate_basename_blocks(self):
        (self.dirs["application"] / "Ui_Actions.py").write_text("# A\n")
        (self.dirs["project"] / "ui_actions.PY").write_text("# B\n")
        self.assertIn("duplicate_hook_basename", self.codes())

    def test_unmanaged_python_symlink_blocks(self):
        (self.dirs["application"] / "actions.py").symlink_to(self.source)
        self.assertIn("hook_file_symlink_present", self.codes())

    def test_dangling_bootstrap_link_is_not_ignored(self):
        (self.dirs["user"] / "dgpy_bootstrap.py").symlink_to(self.base / "never-there")
        self.assertIn("dgpy_candidate_present", self.codes())

    def test_other_dgpy_names_block_as_conservative_candidates(self):
        (self.dirs["application"] / "dgpy_extension.py").write_text("# unknown\n")
        self.assertIn("dgpy_candidate_present", self.codes())

    def test_scope_extra_supported_without_leaking_label(self):
        extra = self.base / "extra"
        extra.mkdir()
        roots = (*self.roots, HookRoot("extra", extra))
        self.assertEqual(self.report(roots=roots).status, "PREVIEW_ONLY")
        (extra / "dgpy_probe.py").write_text("# probe\n")
        report = self.report(roots=roots)
        self.assertIn("dgpy_candidate_present", {f.code for f in report.findings})
        self.assertTrue(all(f.scope in (None, "user", "project", "application", "shared", "extra")
                            for f in report.findings))

    def test_duplicate_root_path_and_identity_block(self):
        roots = tuple(
            HookRoot(r.scope, self.dirs["user"] if r.scope == "shared" else r.path)
            for r in self.roots
        )
        self.assertIn("duplicate_root_path", self.codes(roots=roots))
        self.assertIn("duplicate_root_identity", self.codes(roots=roots))

    def test_root_symlink_blocks_even_to_existing_directory(self):
        link = self.base / "linked"
        link.symlink_to(self.dirs["shared"], target_is_directory=True)
        roots = tuple(HookRoot(r.scope, link if r.scope == "shared" else r.path) for r in self.roots)
        self.assertIn("root_path_contains_symlink", self.codes(roots=roots))

    def test_symlink_ancestor_blocks(self):
        top = self.base / "anchor"
        top.symlink_to(self.base, target_is_directory=True)
        roots = tuple(HookRoot(r.scope, top / "shared" if r.scope == "shared" else r.path)
                      for r in self.roots)
        self.assertIn("root_path_contains_symlink", self.codes(roots=roots))

    def test_source_symlink_blocks(self):
        link = self.base / "source-link" / "dgpy_bootstrap.py"
        link.parent.mkdir()
        link.symlink_to(self.source)
        self.assertIn("source_path_contains_symlink", self.codes(source=link))

    def test_missing_or_wrong_source_blocks(self):
        missing = self.base / "no-checkout" / "dgpy_bootstrap.py"
        self.assertIn("source_missing", self.codes(source=missing))
        wrong = self.base / "not_bootstrap.py"
        wrong.write_text("# not the expected entry\n")
        self.assertIn("unexpected_source_name", self.codes(source=wrong))

    def test_source_inside_hook_root_blocks(self):
        source = self.dirs["shared"] / "dgpy_bootstrap.py"
        source.write_text("# not an external source\n")
        self.assertIn("source_inside_hook_root", self.codes(source=source))

    def test_relative_root_and_path_traversal_block(self):
        roots = tuple(HookRoot(r.scope, Path("relative") if r.scope == "shared" else r.path)
                      for r in self.roots)
        self.assertIn("unknown_or_invalid_root", self.codes(roots=roots))
        roots = tuple(HookRoot(r.scope, self.base / ".." / "shared") if r.scope == "shared" else r
                      for r in self.roots)
        self.assertIn("unknown_or_invalid_root", self.codes(roots=roots))

    def test_world_writable_root_stops_without_chmod(self):
        root = self.dirs["shared"]
        root.chmod(0o777)
        self.addCleanup(lambda: root.chmod(0o755))
        self.assertIn("world_writable_hook_root", self.codes())
        self.assertEqual(root.stat().st_mode & 0o777, 0o777)

    def test_world_writable_source_stops_without_chmod(self):
        self.source.chmod(0o666)
        self.addCleanup(lambda: self.source.chmod(0o644))
        self.assertIn("source_world_writable", self.codes())
        self.assertEqual(self.source.stat().st_mode & 0o777, 0o666)

    def test_unreadable_root_or_file_root_fails_closed(self):
        source = self.base / "not-a-directory"
        source.write_text("something\n")
        roots = tuple(HookRoot(r.scope, source if r.scope == "shared" else r.path)
                      for r in self.roots)
        self.assertIn("root_not_directory", self.codes(roots=roots))
        with patch("dg_python_scripts.deployment.preflight.os.scandir", side_effect=PermissionError):
            self.assertIn("root_inspection_failed", self.codes())

    def test_result_never_contains_private_file_paths(self):
        (self.dirs["shared"] / "dgpy_private_organizer.py").write_text("# private\n")
        report = self.report()
        self.assertNotIn(str(self.base), repr(report))
        self.assertNotIn("private_organizer", repr(report))

    def test_inspection_does_not_mutate_fixture_tree(self):
        before = sorted(str(p.relative_to(self.base)) for p in self.base.rglob("*"))
        self.report()
        after = sorted(str(p.relative_to(self.base)) for p in self.base.rglob("*"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
