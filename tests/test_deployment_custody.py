"""Disposable/in-memory key-custody and recovery preview tests."""

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from dg_python_scripts.deployment.custody_review import (
    CustodyReviewEvidence,
    KeyCustodySnapshot,
    RecoveryPreview,
    assess_recovery_preview,
)
from dg_python_scripts.deployment.anchor_review import JournalAnchor
from dg_python_scripts.deployment.journal_review import JournalReview
from dg_python_scripts.deployment.preflight import Finding


UNTOUCHED = object()


class CustodyReviewTests(unittest.TestCase):
    def setUp(self):
        self.custody = KeyCustodySnapshot(
            protocol="DGpy-Key-Custody-v1", flame_version="2026.2.3",
            scope="user", transaction_id="fixture-tx", key_id="fixture-key",
            generation=1, state="ACTIVE", current_revision=1,
        )
        self.evidence = CustodyReviewEvidence(
            custody_origin_verified=True,
            revocation_status_verified=True,
            latest_revision_verified=True,
            anchor_origin_verified=True,
            isolated_environment_confirmed=True,
            expected_scope="user", expected_transaction_id="fixture-tx",
            expected_key_id="fixture-key", expected_generation=1,
            expected_revision=1,
        )
        self.anchor = JournalAnchor(
            protocol="DGpy-Hook-Anchor-v1", flame_version="2026.2.3",
            scope="user", key_id="fixture-key", transaction_id="fixture-tx",
            revision=1, event_count=3, terminal_state="ACTIVE",
            tip_sha256="a" * 64, mac_sha256="b" * 64,
        )
        self.events = ("mock-event",)
        self.key = bytes(range(32))  # public fixture only, never a real key

    def review(self, *, custody=UNTOUCHED, evidence=UNTOUCHED, anchor=UNTOUCHED,
               key=UNTOUCHED, events=UNTOUCHED, nested=UNTOUCHED):
        value = JournalReview((), "ACTIVE") if nested is UNTOUCHED else nested
        with patch("dg_python_scripts.deployment.custody_review.assess_hmac_journal_preview",
                   return_value=value) as verifier:
            result = assess_recovery_preview(
                custody=self.custody if custody is UNTOUCHED else custody,
                evidence=self.evidence if evidence is UNTOUCHED else evidence,
                anchor=self.anchor if anchor is UNTOUCHED else anchor,
                trusted_key=self.key if key is UNTOUCHED else key,
                events=self.events if events is UNTOUCHED else events,
            )
        return result, verifier

    def blocked(self, expected, **kwargs):
        report, verifier = self.review(**kwargs)
        self.assertEqual(report.status, "BLOCKED")
        self.assertEqual(report.next_step, "MANUAL_RECONCILIATION")
        self.assertIn(expected, [finding.code for finding in report.findings])
        self.assertIsNone(report.terminal_state)
        verifier.assert_not_called()

    def test_nominal_active_preview_is_nonactionable(self):
        report, verifier = self.review()
        self.assertEqual(report.status, "PREVIEW_ONLY")
        self.assertEqual(report.next_step, "NO_CHANGE")
        self.assertEqual(report.terminal_state, "ACTIVE")
        self.assertFalse(hasattr(report, "apply"))
        self.assertFalse(hasattr(report, "disable"))
        self.assertFalse(hasattr(report, "restore"))
        verifier.assert_called_once()
        args = verifier.call_args.kwargs
        self.assertIs(args["events"], self.events)
        self.assertIs(args["anchor"], self.anchor)
        self.assertIs(args["trusted_key"], self.key)
        self.assertEqual(args["evidence"].expected_revision, 1)
        self.assertEqual(args["evidence"].expected_scope, "user")
        self.assertEqual(args["evidence"].expected_key_id, "fixture-key")
        self.assertEqual(args["evidence"].expected_transaction_id, "fixture-tx")
        self.assertTrue(args["evidence"].isolated_environment_confirmed)

    def test_nominal_disabled_preview_is_nonactionable(self):
        record = replace(self.custody, current_revision=2)
        evidence = replace(self.evidence, expected_revision=2)
        report, verifier = self.review(
            custody=record, evidence=evidence,
            nested=JournalReview((), "DISABLED"),
        )
        self.assertEqual(report.status, "PREVIEW_ONLY")
        self.assertEqual(report.terminal_state, "DISABLED")
        self.assertEqual(report.next_step, "NO_CHANGE")
        self.assertEqual(verifier.call_args.kwargs["evidence"].expected_revision, 2)

    def test_missing_all_evidence_blocks_before_any_input_access(self):
        class Exploding:
            def __getattribute__(self, key):
                raise AssertionError("untrusted input inspected")
        report, verifier = self.review(
            custody=Exploding(), evidence=CustodyReviewEvidence(),
            anchor=Exploding(), key=Exploding(), events=Exploding(),
        )
        self.assertIn("custody_origin_unverified", [f.code for f in report.findings])
        verifier.assert_not_called()

    def test_invalid_evidence_container(self):
        self.blocked("invalid_custody_evidence", evidence={})

    def test_hostile_evidence_subclass(self):
        class Hostile(CustodyReviewEvidence):
            def __getattribute__(self, key):
                raise AssertionError("subclass getter")
        self.blocked("invalid_custody_evidence", evidence=Hostile())

    def test_truthy_string_is_not_custody_attestation(self):
        self.blocked("custody_origin_unverified", evidence=replace(
            self.evidence, custody_origin_verified="yes"))

    def test_missing_revocation_attestation(self):
        self.blocked("revocation_status_unverified", evidence=replace(
            self.evidence, revocation_status_verified=False))

    def test_missing_revision_attestation(self):
        self.blocked("latest_revision_unverified", evidence=replace(
            self.evidence, latest_revision_verified=False))

    def test_missing_anchor_attestation(self):
        self.blocked("anchor_origin_unverified", evidence=replace(
            self.evidence, anchor_origin_verified=False))

    def test_missing_isolation_attestation(self):
        self.blocked("isolated_environment_unconfirmed", evidence=replace(
            self.evidence, isolated_environment_confirmed=False))

    def test_unknown_expected_scope(self):
        self.blocked("invalid_expected_scope", evidence=replace(
            self.evidence, expected_scope="project"))

    def test_invalid_expected_key_id(self):
        self.blocked("invalid_expected_key_id", evidence=replace(
            self.evidence, expected_key_id="private/path"))

    def test_invalid_expected_transaction(self):
        self.blocked("invalid_expected_transaction_id", evidence=replace(
            self.evidence, expected_transaction_id=""))

    def test_expected_generation_rejects_rotation(self):
        self.blocked("unsupported_expected_key_generation", evidence=replace(
            self.evidence, expected_generation=2))

    def test_expected_generation_rejects_bool(self):
        self.blocked("unsupported_expected_key_generation", evidence=replace(
            self.evidence, expected_generation=True))

    def test_expected_revision_requires_exact_int(self):
        self.blocked("invalid_expected_revision", evidence=replace(
            self.evidence, expected_revision=True))

    def test_expected_revision_out_of_range(self):
        self.blocked("invalid_expected_revision", evidence=replace(
            self.evidence, expected_revision=3))

    def test_missing_custody_record(self):
        self.blocked("missing_or_invalid_custody_snapshot", custody=None)

    def test_hostile_custody_subclass(self):
        class Hostile(KeyCustodySnapshot):
            def __getattribute__(self, key):
                raise AssertionError("subclass getter")
        self.blocked("missing_or_invalid_custody_snapshot", custody=Hostile(
            **self.custody.__dict__))

    def test_unknown_protocol(self):
        self.blocked("unknown_custody_protocol_or_flame_version", custody=replace(
            self.custody, protocol="other"))

    def test_wrong_flame_version(self):
        self.blocked("unknown_custody_protocol_or_flame_version", custody=replace(
            self.custody, flame_version="2025.2.7"))

    def test_invalid_custody_scope(self):
        self.blocked("invalid_custody_scope", custody=replace(
            self.custody, scope="application"))

    def test_invalid_key_id(self):
        self.blocked("invalid_custody_identity", custody=replace(
            self.custody, key_id="bad/path"))

    def test_invalid_transaction_id(self):
        self.blocked("invalid_custody_identity", custody=replace(
            self.custody, transaction_id=object()))

    def test_rotated_key_generation_is_stopped(self):
        self.blocked("key_rotation_requires_new_protocol", custody=replace(
            self.custody, generation=2))

    def test_key_generation_bool_is_stopped(self):
        self.blocked("key_rotation_requires_new_protocol", custody=replace(
            self.custody, generation=True))

    def test_retired_key_blocks_even_valid_mac(self):
        self.blocked("key_retired_or_revoked", custody=replace(
            self.custody, state="RETIRED"))

    def test_revoked_key_blocks_even_valid_mac(self):
        self.blocked("key_retired_or_revoked", custody=replace(
            self.custody, state="REVOKED"))

    def test_unknown_key_state_stops(self):
        self.blocked("invalid_key_lifecycle_state", custody=replace(
            self.custody, state="MAYBE"))

    def test_bad_key_state_type_stops(self):
        self.blocked("invalid_key_lifecycle_state", custody=replace(
            self.custody, state=object()))

    def test_invalid_custody_revision(self):
        self.blocked("invalid_custody_revision", custody=replace(
            self.custody, current_revision=99))

    def test_custody_revision_bool_stops(self):
        self.blocked("invalid_custody_revision", custody=replace(
            self.custody, current_revision=True))

    def test_swapped_custody_key_stops(self):
        self.blocked("custody_identity_mismatch", custody=replace(
            self.custody, key_id="substituted"))

    def test_swapped_custody_transaction_stops(self):
        self.blocked("custody_identity_mismatch", custody=replace(
            self.custody, transaction_id="other-tx"))

    def test_swapped_custody_scope_stops(self):
        self.blocked("custody_identity_mismatch", custody=replace(
            self.custody, scope="shared"))

    def test_stale_anchor_revision_stops(self):
        self.blocked("custody_revision_mismatch", custody=replace(
            self.custody, current_revision=2))

    def test_underlying_invalid_mac_requires_manual_reconciliation(self):
        report, verifier = self.review(nested=JournalReview((Finding("anchor_mac_mismatch"),)))
        verifier.assert_called_once()
        self.assertEqual(report.status, "BLOCKED")
        self.assertEqual(report.next_step, "MANUAL_RECONCILIATION")
        self.assertEqual([f.code for f in report.findings], ["anchor_mac_mismatch"])
        self.assertIsNone(report.terminal_state)

    def test_interrupted_history_is_never_retried(self):
        report, _ = self.review(nested=JournalReview((Finding("anchor_event_count_mismatch"),)))
        self.assertEqual(report.status, "BLOCKED")
        self.assertEqual(report.next_step, "MANUAL_RECONCILIATION")
        self.assertFalse(hasattr(report, "retry"))

    def test_unexpected_underlying_result_type_blocks(self):
        report, _ = self.review(nested={"status": "PREVIEW_ONLY"})
        self.assertEqual(report.status, "BLOCKED")
        self.assertIn("invalid_anchor_review_result", [x.code for x in report.findings])

    def test_wrong_underlying_terminal_state_blocks(self):
        report, _ = self.review(nested=JournalReview((), "DISABLED"))
        self.assertEqual(report.status, "BLOCKED")
        self.assertIn("custody_anchor_terminal_mismatch", [x.code for x in report.findings])

    def test_underlying_absent_terminal_state_blocks(self):
        report, _ = self.review(nested=JournalReview((), None))
        self.assertEqual(report.status, "BLOCKED")

    def test_no_leaked_sensitive_metadata(self):
        report, _ = self.review(custody=replace(self.custody, transaction_id="private-path"))
        dump = repr(report)
        for thing in ("private-path", self.custody.key_id, self.custody.transaction_id,
                      str(self.key), self.anchor.mac_sha256):
            self.assertNotIn(thing, dump)

    def test_no_fs_mutations_or_reads_in_wrapper(self):
        with patch.object(Path, "open", side_effect=AssertionError("no disk")), \
             patch.object(Path, "unlink", side_effect=AssertionError("no disk")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("no disk")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("no disk")):
            report, _ = self.review()
            self.assertEqual(report.status, "PREVIEW_ONLY")

    def test_user_input_is_not_modified(self):
        snapshot = self.custody
        evidence = self.evidence
        report, _ = self.review()
        self.assertEqual(report.status, "PREVIEW_ONLY")
        self.assertEqual(snapshot, self.custody)
        self.assertEqual(evidence, self.evidence)
        self.assertEqual(self.events, ("mock-event",))


if __name__ == "__main__":
    unittest.main()
