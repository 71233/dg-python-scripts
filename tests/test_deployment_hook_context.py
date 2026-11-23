"""Read-only Hook context identity checks on synthetic, private-free fixtures."""

from dataclasses import replace
import builtins
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from dg_python_scripts.deployment.hook_context_review import (
    RootSnapshot, HookContextRecord, HookContextEvidence,
    assess_hook_context_preview,
)

M = stat.S_IFDIR | 0o755
W = stat.S_IFDIR | 0o777
ROOTS = (
    RootSnapshot("user", "/fixture/user/hooks", True, 1, 10, 501, M),
    RootSnapshot("project", "/fixture/project/hooks", False),
    RootSnapshot("application", "/fixture/app/hooks", True, 1, 12, 0, M),
    RootSnapshot("shared", "/fixture/shared/hooks", True, 1, 13, 0, M),
)
E = HookContextEvidence(True, True, True, True, True, True, True, True, True,
                        "fixture-deploy-1", "user")
C = HookContextRecord("fixture-deploy-1", "2026.2.3", "user",
                      "/fixture/user/hooks/dgpy_bootstrap.py",
                      "/fixture/checkout/bootstrap/dgpy_bootstrap.py",
                      "a"*40, "b"*64, ROOTS)


class ContextReviewTests(unittest.TestCase):
    def review(self, binding=C, observed=C, evidence=E):
        return assess_hook_context_preview(binding=binding, observed=observed,
                                           evidence=evidence)

    def block(self, code, binding=C, observed=None, evidence=E):
        result = self.review(binding, binding if observed is None else observed, evidence)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertEqual(result.next_step, "MANUAL_RECONCILIATION")
        self.assertEqual(result.findings[0].code, code)

    def test_user_context_match_is_nonactionable(self):
        r = self.review()
        self.assertEqual((r.status, r.next_step), ("PREVIEW_ONLY", "NO_CHANGE"))
        for name in ("install", "disable", "unlink", "restore", "approve"):
            self.assertFalse(hasattr(r, name))

    def test_shared_target_matches(self):
        shared = replace(C, target_scope="shared",
                         destination="/fixture/shared/hooks/dgpy_bootstrap.py")
        proof = replace(E, expected_target_scope="shared")
        self.assertEqual(self.review(shared, shared, proof).status, "PREVIEW_ONLY")

    def test_extra_search_root_matches(self):
        record = replace(C, roots=C.roots +
                         (RootSnapshot("extra", "/fixture/extra/hooks", True,
                                       2, 42, 501, M),))
        self.assertEqual(self.review(record, record).status, "PREVIEW_ONLY")

    def test_unknown_binding_attestation_blocks_before_reading_inputs(self):
        class Evil:
            def __getattribute__(self, x):
                raise AssertionError("do not touch unverified record")
        r = self.review(Evil(), Evil(), replace(E, binding_origin_verified=False))
        self.assertEqual(r.findings[0].code, "binding_origin_unverified")

    def test_missing_context_attestations_fail_closed(self):
        fields = {
            "live_roots_verified":"effective_roots_unverified",
            "additional_paths_verified":"additional_paths_unverified",
            "effective_sysconfig_verified":"sysconfig_resolution_unverified",
            "shared_failover_state_verified":"shared_failover_state_unverified",
            "project_context_verified":"project_context_unverified",
            "root_metadata_verified":"root_metadata_unverified",
            "source_revision_verified":"source_revision_unverified",
            "isolated_environment_confirmed":"isolated_environment_unconfirmed",
        }
        for attr, code in fields.items():
            with self.subTest(attr=attr):
                self.block(code, evidence=replace(E, **{attr: False}))

    def test_truthy_string_is_not_attestation(self):
        self.block("shared_failover_state_unverified", evidence=replace(
            E, shared_failover_state_verified="yes"))

    def test_invalid_evidence_type(self):
        self.block("invalid_context_evidence", evidence=None)

    def test_evidence_subclass_not_accessed(self):
        class Evil(HookContextEvidence):
            def __getattribute__(self, _):
                raise AssertionError("unexpected attribute access")
        self.block("invalid_context_evidence", evidence=Evil())

    def test_expected_deployment_id_malformed(self):
        self.block("invalid_expected_deployment_id", evidence=replace(
            E, expected_deployment_id="/private/project"))

    def test_target_scope_invalid(self):
        self.block("invalid_expected_target_scope", evidence=replace(
            E, expected_target_scope="project"))

    def test_missing_binding(self):
        r = self.review(binding=None)
        self.assertEqual(r.findings[0].code, "invalid_binding_missing_or_invalid_hook_context")

    def test_malicious_record_subclass_rejected(self):
        class Evil(HookContextRecord):
            def __getattribute__(self, _):
                raise AssertionError("unexpected field")
        r = self.review(binding=Evil(**C.__dict__))
        self.assertEqual(r.findings[0].code, "invalid_binding_missing_or_invalid_hook_context")

    def test_record_id_mismatch(self):
        self.block("binding_deployment_id_mismatch", binding=replace(
            C, deployment_id="fixture-deploy-2"), observed=C)
        self.block("observed_deployment_id_mismatch", observed=replace(
            C, deployment_id="fixture-deploy-2"))

    def test_record_scope_mismatch(self):
        self.block("target_scope_mismatch", evidence=replace(
            E, expected_target_scope="shared"))

    def test_wrong_version_rejected(self):
        self.block("invalid_binding_unvalidated_flame_version", binding=replace(
            C, flame_version="2025.2.7"))

    def test_relative_or_parent_path_rejected(self):
        for path in ("fixture/hooks", "/fixture/../hooks", "/fixture/./hooks",
                     "/fixture//hooks", "//fixture/hooks", "/", "/fixture/hooks/"):
            with self.subTest(path=path):
                roots = (replace(ROOTS[0], path=path), *ROOTS[1:])
                self.block("invalid_binding_invalid_root_path", binding=replace(C, roots=roots))

    def test_world_writable_root_blocks(self):
        roots = (replace(ROOTS[0], mode=W), *ROOTS[1:])
        self.block("invalid_binding_world_writable_hook_root", binding=replace(C, roots=roots))

    def test_required_shared_root_absent(self):
        roots = (*ROOTS[:3], RootSnapshot("shared", "/fixture/shared/hooks", False))
        self.block("invalid_binding_required_hook_root_absent", binding=replace(C, roots=roots))

    def test_target_missing_even_if_user_optional(self):
        roots = (RootSnapshot("user", "/fixture/user/hooks", False), *ROOTS[1:])
        self.block("invalid_binding_required_hook_root_absent", binding=replace(C, roots=roots))

    def test_optional_non_target_user_absent(self):
        roots = (RootSnapshot("user", "/fixture/user/hooks", False), *ROOTS[1:])
        shared = replace(C, roots=roots, target_scope="shared",
                         destination="/fixture/shared/hooks/dgpy_bootstrap.py")
        self.assertEqual(self.review(shared, shared,
                                    replace(E, expected_target_scope="shared")).status,
                         "PREVIEW_ONLY")

    def test_absent_root_still_with_identity_blocks(self):
        roots = (*ROOTS[:1], replace(ROOTS[1], inode=20), *ROOTS[2:])
        self.block("invalid_binding_absent_root_has_identity", binding=replace(C, roots=roots))

    def test_missing_standard_scope_blocks(self):
        roots = (ROOTS[0], ROOTS[1], ROOTS[2],
                 RootSnapshot("extra", "/fixture/extra/hooks", True, 2, 2, 501, M))
        self.block("invalid_binding_missing_standard_hook_scope", binding=replace(C, roots=roots))

    def test_duplicate_scope_blocks(self):
        roots = C.roots + (replace(ROOTS[0], path="/fixture/another/hooks", inode=90),)
        self.block("invalid_binding_duplicate_standard_scope", binding=replace(C, roots=roots))

    def test_duplicate_root_case_folded_path(self):
        roots = C.roots + (RootSnapshot("extra", "/fixture/USER/hooks", True, 2, 90, 0, M),)
        self.block("invalid_binding_duplicate_root_path", binding=replace(C, roots=roots))

    def test_duplicate_device_inode_blocks(self):
        roots = C.roots + (RootSnapshot("extra", "/fixture/elsewhere/hooks", True, 1, 10, 0, M),)
        self.block("invalid_binding_duplicate_root_identity", binding=replace(C, roots=roots))

    def test_nested_search_roots_block(self):
        roots = C.roots + (RootSnapshot("extra", "/fixture/shared/hooks/nested", True, 2, 99, 0, M),)
        self.block("invalid_binding_overlapping_hook_roots", binding=replace(C, roots=roots))

    def test_source_inside_search_root_blocks(self):
        inside = replace(C, source="/fixture/shared/hooks/dgpy_bootstrap.py")
        self.block("invalid_binding_source_inside_hook_root", binding=inside)

    def test_destination_outside_selected_root_blocks(self):
        self.block("invalid_binding_destination_not_selected_bootstrap", binding=replace(
            C, destination="/fixture/elsewhere/dgpy_bootstrap.py"))

    def test_wrong_source_revision_syntax_blocks(self):
        self.block("invalid_binding_invalid_source_revision", binding=replace(
            C, source_revision="dirty"))

    def test_wrong_source_digest_syntax_blocks(self):
        self.block("invalid_binding_invalid_source_digest", binding=replace(
            C, source_sha256="BAD-DIGEST"))

    def test_source_revision_mismatch_blocks(self):
        self.block("hook_context_snapshot_mismatch", observed=replace(C, source_revision="c"*40))

    def test_source_digest_mismatch_blocks(self):
        self.block("hook_context_snapshot_mismatch", observed=replace(C, source_sha256="c"*64))

    def test_root_inode_mismatch_blocks(self):
        roots = (replace(ROOTS[0], inode=55), *ROOTS[1:])
        self.block("hook_context_snapshot_mismatch", observed=replace(C, roots=roots))

    def test_root_owner_or_mode_mismatch_blocks(self):
        roots = (replace(ROOTS[0], owner_uid=502), *ROOTS[1:])
        self.block("hook_context_snapshot_mismatch", observed=replace(C, roots=roots))
        roots = (replace(ROOTS[0], mode=stat.S_IFDIR | 0o700), *ROOTS[1:])
        self.block("hook_context_snapshot_mismatch", observed=replace(C, roots=roots))

    def test_search_root_order_mismatch_blocks(self):
        roots = (ROOTS[2], ROOTS[1], ROOTS[0], ROOTS[3])
        self.block("hook_context_snapshot_mismatch", observed=replace(C, roots=roots))

    def test_symlink_and_failover_unknown_are_not_assumed_safe(self):
        self.block("root_metadata_unverified", evidence=replace(E, root_metadata_verified=False))
        self.block("shared_failover_state_unverified", evidence=replace(
            E, shared_failover_state_verified=False))

    def test_no_os_or_path_io(self):
        with patch.object(builtins, "open", side_effect=AssertionError("no IO")), \
             patch.object(Path, "lstat", side_effect=AssertionError("no IO")), \
             patch.object(Path, "resolve", side_effect=AssertionError("no IO")):
            self.assertEqual(self.review().status, "PREVIEW_ONLY")

    def test_no_sensitive_paths_in_result(self):
        r = self.review(observed=replace(C, source_sha256="c"*64))
        t = repr(r)
        for private in (C.destination, C.source, ROOTS[0].path, C.deployment_id):
            self.assertNotIn(private, t)

    def test_no_actual_provenance_is_authenticated_by_a_match(self):
        # A matched pair of self-asserted records can be fabricated. This
        # demonstrates why only independent, authentic sources may attest.
        fake = replace(C, deployment_id="fabricated-but-consistent")
        proof = replace(E, expected_deployment_id="fabricated-but-consistent")
        self.assertEqual(self.review(fake, fake, proof).status, "PREVIEW_ONLY")
        self.assertEqual(self.review(fake, fake, proof).next_step, "NO_CHANGE")


if __name__ == "__main__":
    unittest.main()
