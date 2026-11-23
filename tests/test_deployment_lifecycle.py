"""Disposable filesystem tests of read-only managed-link disable previews."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dg_python_scripts.deployment import (
    DisableReviewEvidence,
    FileIdentity,
    ManagedLinkRecord,
    assess_disable_preview,
)


def identity(path):
    st = path.lstat()
    return FileIdentity(st.st_dev, st.st_ino, st.st_uid)


class LifecyclePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dgpy-disable-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "user-hook"
        self.root.mkdir()
        self.source = self.base / "checkout" / "bootstrap" / "dgpy_bootstrap.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("# fixture-only source\n")
        self.link = self.root / "dgpy_bootstrap.py"
        self.link.symlink_to(self.source)
        self.record = ManagedLinkRecord(
            flame_version="2026.2.3",
            scope="user",
            state="ACTIVE",
            transaction_id="test-transaction",
            hook_root=self.root,
            destination=self.link,
            source=self.source,
            raw_link_target=str(self.source),
            root_identity=identity(self.root),
            link_identity=identity(self.link),
            source_identity=identity(self.source),
            source_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
        )
        self.evidence = DisableReviewEvidence(True, True, True, True)

    def review(self, record=None, evidence=None):
        return assess_disable_preview(
            record=self.record if record is None else record,
            evidence=self.evidence if evidence is None else evidence,
        )

    def codes(self, record=None, evidence=None):
        return {f.code for f in self.review(record, evidence).findings}

    def test_record_match_is_non_actionable_preview(self):
        r = self.review()
        self.assertEqual(r.status, "PREVIEW_ONLY")
        self.assertEqual(r.findings, ())
        self.assertFalse(hasattr(r, "apply"))
        self.assertFalse(hasattr(r, "disable"))
        self.assertTrue(self.link.is_symlink())

    def test_default_evidence_blocks(self):
        codes = self.codes(evidence=DisableReviewEvidence())
        self.assertEqual(codes, {
            "journal_not_authenticated",
            "effective_roots_unreviewed",
            "ownership_acl_mount_unreviewed",
            "isolated_environment_unconfirmed",
        })

    def test_missing_evidence_does_not_touch_any_filesystem_path(self):
        with patch("dg_python_scripts.deployment.lifecycle.Path.lstat", side_effect=AssertionError("unsafe read")):
            self.assertEqual(self.review(evidence=DisableReviewEvidence()).status, "BLOCKED")

    def test_truthy_string_is_not_authorization(self):
        ev = replace(self.evidence, journal_authenticated="yes")
        self.assertIn("journal_not_authenticated", self.codes(evidence=ev))

    def test_missing_record_blocks(self):
        r = assess_disable_preview(record=None, evidence=self.evidence)
        self.assertEqual(r.status, "BLOCKED")
        self.assertIn("missing_or_invalid_managed_record", {x.code for x in r.findings})

    def test_invalid_evidence_type_blocks(self):
        r = assess_disable_preview(record=self.record, evidence=None)
        self.assertIn("invalid_review_evidence", {x.code for x in r.findings})

    def test_wrong_type_record_blocks(self):
        r = assess_disable_preview(record={}, evidence=self.evidence)
        self.assertIn("missing_or_invalid_managed_record", {x.code for x in r.findings})

    def test_unsupported_scope_blocks(self):
        self.assertIn("unsupported_record_scope", self.codes(replace(self.record, scope="application")))

    def test_unhashable_scope_blocks(self):
        self.assertIn("unsupported_record_scope", self.codes(replace(self.record, scope=[])))

    def test_wrong_flame_version_blocks(self):
        self.assertIn("unvalidated_record_version", self.codes(replace(self.record, flame_version="2025.2.7")))

    def test_inactive_state_blocks(self):
        self.assertIn("record_not_active", self.codes(replace(self.record, state="DISABLED")))

    def test_missing_transaction_blocks(self):
        self.assertIn("missing_transaction_id", self.codes(replace(self.record, transaction_id=" ")))

    def test_malformed_identity_blocks(self):
        self.assertIn("invalid_recorded_identity", self.codes(replace(self.record, root_identity=None)))
        self.assertIn("invalid_recorded_identity", self.codes(replace(
            self.record, root_identity=FileIdentity(True, 1, 1)
        )))

    def test_invalid_recorded_digest_blocks(self):
        self.assertIn("invalid_recorded_source_digest", self.codes(replace(
            self.record, source_sha256="not-a-hash"
        )))

    def test_source_replaced_at_same_path_blocks(self):
        self.source.unlink()
        self.source.write_text("replacement")
        # Filesystems may immediately recycle an inode; the hash still differs.
        self.assertIn("source_digest_changed", self.codes())

    def test_source_edited_in_place_blocks(self):
        self.source.write_text("changed in place")
        self.assertIn("source_digest_changed", self.codes())

    def test_relative_destination_blocks(self):
        self.assertIn("invalid_record_paths", self.codes(replace(self.record, destination=Path("dgpy_bootstrap.py"))))

    def test_outside_directory_destination_blocks(self):
        self.assertIn("invalid_record_paths", self.codes(replace(self.record, destination=self.base / "dgpy_bootstrap.py")))

    def test_non_bootstrap_destination_blocks(self):
        self.assertIn("invalid_record_paths", self.codes(replace(self.record, destination=self.root / "other.py")))

    def test_non_bootstrap_source_blocks(self):
        self.assertIn("invalid_record_paths", self.codes(replace(self.record, source=self.base / "other.py")))

    def test_source_inside_root_blocks(self):
        inside = self.root / "dgpy_bootstrap.py"
        self.assertIn("invalid_record_paths", self.codes(replace(self.record, source=inside)))

    def test_link_target_mismatch_blocks(self):
        self.assertIn("invalid_record_link_target", self.codes(replace(self.record, raw_link_target="/other/private/path")))

    def test_relative_link_target_is_rejected(self):
        self.assertIn("invalid_record_link_target", self.codes(replace(self.record, raw_link_target="../x")))

    def test_root_metadata_mismatch_blocks(self):
        wrong = replace(self.record.root_identity, inode=1)
        self.assertIn("hook_root_identity_changed", self.codes(replace(self.record, root_identity=wrong)))

    def test_link_metadata_mismatch_blocks(self):
        wrong = replace(self.record.link_identity, inode=1)
        self.assertIn("managed_link_identity_changed", self.codes(replace(self.record, link_identity=wrong)))

    def test_link_replaced_with_regular_file_blocks(self):
        self.link.unlink()  # Fixture setup only, production module never unlinks.
        self.link.write_text("keep me")
        self.assertIn("managed_link_not_symlink", self.codes())
        self.assertEqual(self.link.read_text(), "keep me")

    def test_link_missing_blocks_without_recreate(self):
        self.link.unlink()
        self.assertIn("managed_link_inspection_failed", self.codes())
        self.assertFalse(self.link.exists())

    def test_link_target_retarget_blocks(self):
        self.link.unlink()
        new_source = self.base / "unknown.py"
        new_source.write_text("unknown")
        self.link.symlink_to(new_source)
        result = self.codes()
        self.assertTrue({"managed_link_identity_changed", "managed_link_target_changed"} <= result)

    def test_root_missing_blocks(self):
        self.link.unlink()
        self.root.rmdir()
        self.assertIn("hook_root_inspection_failed", self.codes())

    def test_world_writable_root_blocks_without_chmod(self):
        self.root.chmod(0o777)  # Fixture only.
        self.assertIn("world_writable_hook_root", self.codes())
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o777)

    def test_world_writable_source_blocks_without_chmod(self):
        self.source.chmod(0o666)  # Fixture only.
        self.assertIn("source_world_writable", self.codes())
        self.assertEqual(self.source.stat().st_mode & 0o777, 0o666)

    def test_symlinked_root_blocks(self):
        alias = self.base / "root-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertIn("hook_root_alias_present", self.codes(replace(
            self.record, hook_root=alias, destination=alias / self.link.name
        )))

    def test_symlinked_parent_blocks(self):
        alias = self.base / "alias"
        alias.symlink_to(self.base, target_is_directory=True)
        self.assertIn("hook_root_alias_present", self.codes(replace(
            self.record, hook_root=alias / self.root.name,
            destination=alias / self.root.name / self.link.name
        )))

    def test_symlinked_source_blocks(self):
        source_alias = self.base / "source-alias" / "dgpy_bootstrap.py"
        source_alias.parent.mkdir()
        source_alias.symlink_to(self.source)
        self.link.unlink()
        self.link.symlink_to(source_alias)
        record = replace(
            self.record, source=source_alias, raw_link_target=str(source_alias),
            link_identity=identity(self.link),
        )
        self.assertIn("source_alias_present", self.codes(record))

    def test_unexpectedly_large_source_blocks_before_open(self):
        self.source.write_bytes(b"x" * (1024 * 1024 + 1))
        with patch("dg_python_scripts.deployment.lifecycle.os.open", side_effect=AssertionError("unexpected open")):
            self.assertIn("source_unexpectedly_large", self.codes())

    def test_readonly_open_failure_blocks(self):
        with patch("dg_python_scripts.deployment.lifecycle.os.open", side_effect=PermissionError("denied")):
            self.assertIn("source_inspection_failed", self.codes())

    def test_source_missing_blocks(self):
        self.source.unlink()
        self.assertIn("source_inspection_failed", self.codes())

    def test_private_paths_never_in_findings(self):
        self.link.unlink()
        self.link.write_text("unmanaged")
        report = self.review()
        rendered = repr(report)
        for private in (str(self.base), str(self.root), str(self.source), str(self.link)):
            self.assertNotIn(private, rendered)

    def test_no_write_methods_called_by_review(self):
        with patch.object(Path, "unlink", side_effect=AssertionError("unlink")), \
             patch.object(Path, "symlink_to", side_effect=AssertionError("symlink_to")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write_text")):
            self.assertEqual(self.review().status, "PREVIEW_ONLY")

    def test_no_mutations_during_preview(self):
        before = sorted((p.relative_to(self.base).as_posix(), p.lstat().st_mode) for p in self.base.rglob("*"))
        self.assertEqual(self.review().status, "PREVIEW_ONLY")
        after = sorted((p.relative_to(self.base).as_posix(), p.lstat().st_mode) for p in self.base.rglob("*"))
        self.assertEqual(before, after)

    def test_permission_failure_blocks(self):
        original = Path.lstat

        def bad_stat(path, *args, **kwargs):
            if path == self.root:
                raise PermissionError("mock blocked")
            return original(path, *args, **kwargs)

        with patch("dg_python_scripts.deployment.lifecycle.Path.lstat", bad_stat):
            self.assertIn("hook_root_inspection_failed", self.codes())

    def test_source_failure_blocks(self):
        original = Path.lstat

        def bad_stat(path, *args, **kwargs):
            if path == self.source:
                raise PermissionError("mock blocked")
            return original(path, *args, **kwargs)

        with patch("dg_python_scripts.deployment.lifecycle.Path.lstat", bad_stat):
            self.assertIn("source_inspection_failed", self.codes())


if __name__ == "__main__":
    unittest.main()
