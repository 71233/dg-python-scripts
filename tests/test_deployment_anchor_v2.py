"""Isolated read-only v2 HMAC tests with PUBLIC deterministic fixture bytes."""

from dataclasses import replace
import builtins
import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

from dg_python_scripts.deployment.anchor_v2_review import (
    V2Anchor, V2Evidence, V2KeyState, assess_v2_anchor_preview,
)
from dg_python_scripts.deployment.journal_review import JournalEvent

# Public deterministic bytes for a test only; no operational secrets.
TEST_KEY = bytes(range(32))
ORDER = ("INTENT", "LINK_CREATED", "ACTIVE", "DISABLE_INTENT", "DISABLED")
DOMAIN_V2 = b"DGpy Hook Anchor HMAC-SHA256 v2\n"
DOMAIN_V1 = b"DGpy Hook Anchor HMAC-SHA256 v1\n"
CHAIN_DOMAIN = b"DGpy Hook Journal v1\n"


def sample_events(count=3, transaction_id="fixture-tx"):
    previous = "0" * 64
    result = []
    for i in range(count):
        payload_hash = hashlib.sha256(("test-payload-%d" % i).encode()).hexdigest()
        payload = [i, transaction_id, ORDER[i], payload_hash, previous]
        digest = hashlib.sha256(CHAIN_DOMAIN + json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"),
        ).encode("ascii")).hexdigest()
        result.append(JournalEvent(*payload, digest))
        previous = digest
    return result


def sign_fixture(anchor, key=TEST_KEY, domain=DOMAIN_V2):
    """Only test fixtures may sign; production API intentionally cannot."""
    payload = [anchor.protocol, anchor.flame_version, anchor.scope,
               anchor.deployment_id, anchor.transaction_id, anchor.key_id,
               anchor.key_generation, anchor.revision, anchor.event_count, anchor.terminal_state,
               anchor.tip_sha256]
    digest = hmac.new(key, domain + json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii"), hashlib.sha256).hexdigest()
    return replace(anchor, mac_sha256=digest)


def make_fixture(generation=2, count=3, scope="user", transaction="fixture-tx",
                 deployment="fixture-deployment-A"):
    events = sample_events(count, transaction)
    revision = 1 if count == 3 else 2
    terminal = "ACTIVE" if count == 3 else "DISABLED"
    tip = events[-1].event_sha256
    anchor = sign_fixture(V2Anchor(
        protocol="DGpy-Hook-Anchor-v2", flame_version="2026.2.3",
        scope=scope, deployment_id=deployment,
        transaction_id=transaction, key_id="fixture-key-v2",
        key_generation=generation, revision=revision, event_count=count,
        terminal_state=terminal, tip_sha256=tip, mac_sha256="0" * 64,
    ))
    state = V2KeyState(
        protocol="DGpy-Key-Custody-v2", flame_version="2026.2.3",
        scope=scope, deployment_id=deployment,
        transaction_id=transaction, key_id="fixture-key-v2",
        generation=generation, lifecycle_state="ACTIVE",
        latest_revision=revision, latest_tip_sha256=tip,
    )
    evidence = V2Evidence(
        key_origin_verified=True, key_status_verified=True,
        checkpoint_origin_verified=True, anchor_origin_verified=True,
        isolated_environment_confirmed=True, expected_scope=scope,
        expected_deployment_id=deployment, expected_transaction_id=transaction,
        expected_key_id="fixture-key-v2",
        expected_generation=generation, expected_revision=revision,
        expected_tip_sha256=tip,
    )
    return events, state, anchor, evidence


class AnchorV2Tests(unittest.TestCase):
    def setUp(self):
        self.events, self.state, self.anchor, self.proof = make_fixture()

    def review(self, *, events=None, state=None, anchor=None, proof=None, key=None):
        return assess_v2_anchor_preview(
            events=self.events if events is None else events,
            key_state=self.state if state is None else state,
            anchor=self.anchor if anchor is None else anchor,
            evidence=self.proof if proof is None else proof,
            trusted_key=TEST_KEY if key is None else key,
        )

    def blocked(self, code, **kwargs):
        result = self.review(**kwargs)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertEqual(result.next_step, "MANUAL_RECONCILIATION")
        self.assertIsNone(result.terminal_state)
        self.assertIn(code, [f.code for f in result.findings])

    def test_valid_generation_one(self):
        events, state, anchor, proof = make_fixture(generation=1)
        result = self.review(events=events, state=state, anchor=anchor, proof=proof)
        self.assertEqual((result.status, result.terminal_state, result.next_step),
                         ("PREVIEW_ONLY", "ACTIVE", "NO_CHANGE"))

    def test_valid_generation_two(self):
        result = self.review()
        self.assertEqual((result.status, result.terminal_state, result.next_step),
                         ("PREVIEW_ONLY", "ACTIVE", "NO_CHANGE"))
        for action in ("apply", "disable", "restore", "sign", "write", "unlink"):
            self.assertFalse(hasattr(result, action))

    def test_valid_generation_seven_disabled(self):
        args = make_fixture(generation=7, count=5)
        result = self.review(events=args[0], state=args[1], anchor=args[2], proof=args[3])
        self.assertEqual((result.status, result.terminal_state), ("PREVIEW_ONLY", "DISABLED"))

    def test_shared_scope_bound(self):
        args = make_fixture(scope="shared")
        self.assertEqual(self.review(events=args[0], state=args[1], anchor=args[2], proof=args[3]).status,
                         "PREVIEW_ONLY")

    def test_no_attestation_blocks_without_reading_untrusted_objects(self):
        class Explosive:
            def __getattribute__(self, _):
                raise AssertionError("do not inspect untrusted input")
        result = assess_v2_anchor_preview(
            events=Explosive(), key_state=Explosive(), anchor=Explosive(),
            trusted_key=Explosive(), evidence=V2Evidence(),
        )
        self.assertEqual([x.code for x in result.findings], ["key_origin_unverified"])

    def test_missing_expected_deployment_id_blocks(self):
        self.blocked("invalid_expected_deployment_id", proof=replace(
            self.proof, expected_deployment_id=None))

    def test_deployment_path_as_id_blocks(self):
        self.blocked("invalid_expected_deployment_id", proof=replace(
            self.proof, expected_deployment_id="/private/workstation"))

    def test_deployment_id_rejects_str_subclass(self):
        class EvilId(str):
            pass
        self.blocked("invalid_expected_deployment_id", proof=replace(
            self.proof, expected_deployment_id=EvilId("fixture-deployment-A")))

    def test_wrong_key_state_deployment_blocks(self):
        self.blocked("key_state_identity_mismatch", state=replace(
            self.state, deployment_id="fixture-deployment-B"))

    def test_wrong_anchor_deployment_blocks(self):
        self.blocked("anchor_identity_mismatch", anchor=replace(
            self.anchor, deployment_id="fixture-deployment-B"))

    def test_reused_transaction_wrong_expected_deployment_blocks(self):
        # Even with the same key ID, transaction ID and event tip, the
        # expected deployment must be an independent input.
        proof = replace(self.proof, expected_deployment_id="fixture-deployment-B")
        self.blocked("key_state_identity_mismatch", proof=proof)

    def test_same_key_and_transaction_different_deployments_have_distinct_mac(self):
        _, _, other_anchor, _ = make_fixture(deployment="fixture-deployment-B")
        self.assertNotEqual(self.anchor.mac_sha256, other_anchor.mac_sha256)

    def test_empty_anchor_deployment_blocks(self):
        self.blocked("invalid_anchor_identity", anchor=replace(
            self.anchor, deployment_id=""))

    def test_untrusted_deployment_swap_cannot_reuse_mac(self):
        # Changing the context and external claims without the key fails.
        proof = replace(self.proof, expected_deployment_id="fixture-deployment-B")
        state = replace(self.state, deployment_id="fixture-deployment-B")
        anchor = replace(self.anchor, deployment_id="fixture-deployment-B")
        self.blocked("anchor_v2_mac_mismatch", proof=proof, state=state, anchor=anchor)

    def test_independent_new_deployment_uses_new_mac(self):
        events, state, anchor, proof = make_fixture(deployment="fixture-deployment-B")
        result = self.review(events=events, state=state, anchor=anchor, proof=proof)
        self.assertEqual((result.status, result.next_step), ("PREVIEW_ONLY", "NO_CHANGE"))

    def test_untrusted_key_status_blocks(self):
        self.blocked("key_status_unverified", proof=replace(self.proof, key_status_verified=False))

    def test_untrusted_checkpoint_blocks(self):
        self.blocked("checkpoint_origin_unverified", proof=replace(self.proof, checkpoint_origin_verified=False))

    def test_untrusted_anchor_blocks(self):
        self.blocked("anchor_origin_unverified", proof=replace(self.proof, anchor_origin_verified=False))

    def test_unknown_isolation_blocks(self):
        self.blocked("isolated_environment_unconfirmed", proof=replace(self.proof, isolated_environment_confirmed=False))

    def test_truthy_string_is_not_attestation(self):
        self.blocked("key_origin_unverified", proof=replace(self.proof, key_origin_verified="yes"))

    def test_invalid_proof_type(self):
        self.blocked("invalid_v2_evidence", proof={})

    def test_hostile_proof_subclass_not_accessed(self):
        class Evil(V2Evidence):
            def __getattribute__(self, name):
                raise AssertionError(name)
        self.blocked("invalid_v2_evidence", proof=Evil())

    def test_invalid_scope_evidence(self):
        self.blocked("invalid_expected_scope", proof=replace(self.proof, expected_scope="project"))

    def test_invalid_tx_evidence(self):
        self.blocked("invalid_expected_transaction_id", proof=replace(self.proof, expected_transaction_id="/private/tx"))

    def test_invalid_key_id_evidence(self):
        self.blocked("invalid_expected_key_id", proof=replace(self.proof, expected_key_id=object()))

    def test_zero_generation_evidence(self):
        self.blocked("invalid_expected_generation", proof=replace(self.proof, expected_generation=0))

    def test_bool_generation_evidence(self):
        self.blocked("invalid_expected_generation", proof=replace(self.proof, expected_generation=True))

    def test_overflow_generation_evidence(self):
        self.blocked("invalid_expected_generation", proof=replace(self.proof, expected_generation=2**31))

    def test_invalid_revision_evidence(self):
        self.blocked("invalid_expected_revision", proof=replace(self.proof, expected_revision=3))

    def test_invalid_tip_evidence(self):
        self.blocked("invalid_expected_tip", proof=replace(self.proof, expected_tip_sha256="z"*64))

    def test_bad_state_type(self):
        self.blocked("missing_or_invalid_key_state", state={})

    def test_hostile_state_subclass(self):
        class Evil(V2KeyState):
            def __getattribute__(self, name):
                raise AssertionError(name)
        self.blocked("missing_or_invalid_key_state", state=Evil(**self.state.__dict__))

    def test_wrong_key_state_version(self):
        self.blocked("unsupported_key_state_version", state=replace(self.state, protocol="DGpy-Key-Custody-v1"))

    def test_wrong_flame_version(self):
        self.blocked("unsupported_key_state_version", state=replace(self.state, flame_version="2025.2.7"))

    def test_key_state_scope_invalid(self):
        self.blocked("invalid_key_state_scope", state=replace(self.state, scope="batch"))

    def test_key_state_identity_invalid(self):
        self.blocked("invalid_key_state_identity", state=replace(self.state, key_id="bad/path"))

    def test_key_state_generation_invalid(self):
        self.blocked("invalid_key_state_generation", state=replace(self.state, generation=True))

    def test_key_state_revoked_blocks_before_anchor(self):
        class Evil:
            def __getattribute__(self, _):
                raise AssertionError("should stop before anchor inspection")
        result = assess_v2_anchor_preview(
            events=Evil(), anchor=Evil(), trusted_key=Evil(),
            evidence=self.proof, key_state=replace(self.state, lifecycle_state="REVOKED"),
        )
        self.assertEqual([x.code for x in result.findings], ["key_retired_or_revoked"])

    def test_retired_key_blocks(self):
        self.blocked("key_retired_or_revoked", state=replace(self.state, lifecycle_state="RETIRED"))

    def test_unknown_key_status_blocks(self):
        self.blocked("invalid_key_state_status", state=replace(self.state, lifecycle_state="UNKNOWN"))

    def test_invalid_state_checkpoint_blocks(self):
        self.blocked("invalid_key_state_checkpoint", state=replace(self.state, latest_revision=4))

    def test_substituted_key_generation_blocks(self):
        self.blocked("key_state_identity_mismatch", state=replace(self.state, generation=1))

    def test_key_state_different_tx_blocks(self):
        self.blocked("key_state_identity_mismatch", state=replace(self.state, transaction_id="other"))

    def test_old_key_state_revision_blocks(self):
        self.blocked("key_state_checkpoint_mismatch", state=replace(self.state, latest_revision=2))

    def test_external_tip_mismatch_blocks(self):
        self.blocked("key_state_checkpoint_mismatch", state=replace(self.state, latest_tip_sha256="f"*64))

    def test_bad_anchor_type_blocks(self):
        self.blocked("missing_or_invalid_v2_anchor", anchor={})

    def test_hostile_anchor_subclass(self):
        class Evil(V2Anchor):
            def __getattribute__(self, name):
                raise AssertionError(name)
        self.blocked("missing_or_invalid_v2_anchor", anchor=Evil(**self.anchor.__dict__))

    def test_short_key_blocks(self):
        self.blocked("invalid_trusted_key", key=b"too-short")

    def test_mutable_key_blocks(self):
        self.blocked("invalid_trusted_key", key=bytearray(TEST_KEY))

    def test_wrong_key_mac_blocks(self):
        self.blocked("anchor_v2_mac_mismatch", key=b"Q"*32)

    def test_signed_v1_protocol_rejected(self):
        self.blocked("unsupported_anchor_version", anchor=replace(self.anchor, protocol="DGpy-Hook-Anchor-v1"))

    def test_wrong_anchor_flame_blocks(self):
        self.blocked("unsupported_anchor_version", anchor=replace(self.anchor, flame_version="2025.2.7"))

    def test_anchor_scope_invalid_blocks(self):
        self.blocked("invalid_anchor_scope", anchor=replace(self.anchor, scope="project"))

    def test_bad_anchor_id(self):
        self.blocked("invalid_anchor_identity", anchor=replace(self.anchor, key_id="bad/path"))

    def test_bad_anchor_generation_type(self):
        self.blocked("invalid_anchor_generation", anchor=replace(self.anchor, key_generation=True))

    def test_bad_anchor_terminal_state(self):
        self.blocked("invalid_anchor_terminal_state", anchor=replace(self.anchor, terminal_state="LINK_CREATED"))

    def test_invalid_terminal_count(self):
        self.blocked("invalid_anchor_revision_or_count", anchor=replace(self.anchor, event_count=5))

    def test_oversized_anchor_revision(self):
        self.blocked("invalid_anchor_revision_or_count", anchor=replace(self.anchor, revision=9))

    def test_invalid_mac_format(self):
        self.blocked("invalid_anchor_digest", anchor=replace(self.anchor, mac_sha256="NOT-HASH"))

    def test_anchor_generation_mismatch(self):
        self.blocked("anchor_identity_mismatch", anchor=replace(self.anchor, key_generation=1))

    def test_anchor_key_id_substitution(self):
        self.blocked("anchor_identity_mismatch", anchor=replace(self.anchor, key_id="substituted"))

    def test_stale_anchor_revision_blocks(self):
        self.blocked("anchor_checkpoint_mismatch", anchor=replace(self.anchor, revision=2, event_count=5, terminal_state="DISABLED"))

    def test_anchor_tip_mismatch_blocks(self):
        self.blocked("anchor_checkpoint_mismatch", anchor=replace(self.anchor, tip_sha256="a"*64))

    def test_generation_is_cryptographically_mac_bound(self):
        # Alter both anchor generation and *external* expectation, but do
        # not resign: unlike HMAC v1 this must fail specifically at MAC.
        proof=replace(self.proof, expected_generation=3)
        state=replace(self.state, generation=3)
        anchor=replace(self.anchor, key_generation=3)
        self.blocked("anchor_v2_mac_mismatch", anchor=anchor, state=state, proof=proof)

    def test_v1_mac_domain_cannot_validate_as_v2(self):
        old_mac=sign_fixture(self.anchor, domain=DOMAIN_V1)
        self.blocked("anchor_v2_mac_mismatch", anchor=old_mac)

    def test_mismatched_mac_blocks_before_events(self):
        class ExplodingList(list):
            def __len__(self):
                raise AssertionError("events accessed before MAC")
        anchor=replace(self.anchor, mac_sha256="f"*64)
        result=assess_v2_anchor_preview(evidence=self.proof, key_state=self.state,
                                        anchor=anchor, trusted_key=TEST_KEY,
                                        events=ExplodingList())
        self.assertEqual([x.code for x in result.findings], ["anchor_v2_mac_mismatch"])

    def test_non_sequence_events_block(self):
        self.blocked("invalid_journal_collection", events=iter(self.events))

    def test_missing_event_blocks(self):
        self.blocked("journal_count_mismatch", events=self.events[:2])

    def test_tampered_event_blocks(self):
        events=[replace(self.events[0], payload_sha256="f"*64), *self.events[1:]]
        self.blocked("journal_event_digest_mismatch", events=events)

    def test_swapped_event_order_blocks(self):
        events=[self.events[1], self.events[0], self.events[2]]
        self.blocked("journal_sequence_mismatch", events=events)

    def test_report_redacts_key_ids_and_digest(self):
        report=self.review(key=b"X"*32)
        message=repr(report)
        for sensitive in (self.anchor.key_id, self.anchor.transaction_id, self.anchor.mac_sha256, str(TEST_KEY)):
            self.assertNotIn(sensitive, message)

    def test_no_file_reads_or_writes(self):
        with patch.object(builtins, "open", side_effect=AssertionError("filesystem forbidden")):
            self.assertEqual(self.review().status, "PREVIEW_ONLY")

    def test_explicit_limitation_forged_approved_checkpoint_passes(self):
        # Deliberate limitation: malicious authority replacing key, checkpoint
        # and anchor can supply a coherent but fabricated history.
        args=make_fixture(generation=3, transaction="invented-tx")
        self.assertEqual(self.review(events=args[0], state=args[1], anchor=args[2], proof=args[3]).status,
                         "PREVIEW_ONLY")


if __name__ == "__main__":
    unittest.main()
