"""Disposable, in-memory keyed anchor review; never use production keys."""

from dataclasses import replace
import hashlib
import hmac
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from dg_python_scripts.deployment.anchor_review import (
    JournalAnchor, AnchorReviewEvidence, assess_hmac_journal_preview,
)
from dg_python_scripts.deployment.journal_review import JournalEvent


# Public, deterministic TEST FIXTURES, not real secret material.
TEST_KEY = bytes(range(32))
MAC_DOMAIN = b"DGpy Hook Anchor HMAC-SHA256 v1\n"
CHAIN_DOMAIN = b"DGpy Hook Journal v1\n"
S = object()


def make_events(count=3, tx="fixture-tx"):
    order = ("INTENT", "LINK_CREATED", "ACTIVE", "DISABLE_INTENT", "DISABLED")
    old = "0" * 64
    events = []
    for i in range(count):
        payload = hashlib.sha256(("fixture:%d" % i).encode()).hexdigest()
        msg = json.dumps([i, tx, order[i], payload, old],
                         ensure_ascii=True, separators=(",", ":")).encode("ascii")
        digest = hashlib.sha256(CHAIN_DOMAIN + msg).hexdigest()
        events.append(JournalEvent(i, tx, order[i], payload, old, digest))
        old = digest
    return events


def sign_fixture(anchor, key=TEST_KEY):
    """Only a test fixture generator; there is no signer in production API."""
    fields = [anchor.protocol, anchor.flame_version, anchor.scope,
              anchor.key_id, anchor.transaction_id, anchor.revision,
              anchor.event_count, anchor.terminal_state, anchor.tip_sha256]
    message = json.dumps(fields, ensure_ascii=True,
                         separators=(",", ":")).encode("ascii")
    return replace(anchor, mac_sha256=hmac.new(
        key, MAC_DOMAIN + message, hashlib.sha256).hexdigest())


class HmacAnchorReviewTests(unittest.TestCase):
    def setUp(self):
        self.events = make_events()
        self.anchor = sign_fixture(JournalAnchor(
            protocol="DGpy-Hook-Anchor-v1",
            flame_version="2026.2.3",
            scope="user",
            key_id="fixture-key",
            transaction_id="fixture-tx",
            revision=1,
            event_count=3,
            terminal_state="ACTIVE",
            tip_sha256=self.events[-1].event_sha256,
            mac_sha256="0" * 64,
        ))
        self.evidence = AnchorReviewEvidence(
            key_origin_confirmed=True,
            anchor_origin_confirmed=True,
            isolated_environment_confirmed=True,
            expected_key_id="fixture-key",
            expected_transaction_id="fixture-tx",
            expected_scope="user",
            expected_revision=1,
        )

    def review(self, *, anchor=S, evidence=S, key=S, events=S):
        return assess_hmac_journal_preview(
            anchor=self.anchor if anchor is S else anchor,
            evidence=self.evidence if evidence is S else evidence,
            trusted_key=TEST_KEY if key is S else key,
            events=self.events if events is S else events,
        )

    def blocked(self, code, **kw):
        r = self.review(**kw)
        self.assertEqual(r.status, "BLOCKED")
        self.assertIn(code, tuple(f.code for f in r.findings))
        self.assertIsNone(r.terminal_state)

    def test_valid_active_only_preview(self):
        result = self.review()
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertEqual(result.terminal_state, "ACTIVE")
        self.assertFalse(hasattr(result, "apply"))

    def test_valid_disabled_only_preview(self):
        events = make_events(count=5)
        anchor = sign_fixture(replace(
            self.anchor, revision=2, event_count=5,
            terminal_state="DISABLED", tip_sha256=events[-1].event_sha256))
        evidence = replace(self.evidence, expected_revision=2)
        result = self.review(anchor=anchor, evidence=evidence, events=events)
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertEqual(result.terminal_state, "DISABLED")
        self.assertFalse(hasattr(result, "restore"))

    def test_default_evidence_blocks_without_touching_anchor_or_events(self):
        class Exploding:
            def __getattribute__(self, _):
                raise AssertionError("Should not inspect untrusted inputs")
        self.blocked("trusted_key_origin_unconfirmed", anchor=Exploding(),
                     events=Exploding(), evidence=AnchorReviewEvidence())

    def test_anchor_origin_unconfirmed(self):
        self.blocked("anchor_origin_unconfirmed", evidence=replace(self.evidence, anchor_origin_confirmed=False))

    def test_isolation_unconfirmed(self):
        self.blocked("isolated_environment_unconfirmed", evidence=replace(self.evidence, isolated_environment_confirmed=False))

    def test_truthy_flags_not_proof(self):
        self.blocked("trusted_key_origin_unconfirmed", evidence=replace(self.evidence, key_origin_confirmed="yes"))

    def test_invalid_evidence_type(self):
        self.blocked("invalid_anchor_evidence", evidence={})

    def test_evidence_subclass_does_not_get_fields(self):
        class Hostile(AnchorReviewEvidence):
            def __getattribute__(self, name):
                raise AssertionError(name)
        self.blocked("invalid_anchor_evidence", evidence=Hostile())

    def test_invalid_expected_key_id(self):
        self.blocked("invalid_expected_key_id", evidence=replace(self.evidence, expected_key_id="private/key/path"))

    def test_invalid_expected_tx_id(self):
        self.blocked("invalid_expected_transaction_id", evidence=replace(self.evidence, expected_transaction_id=" "))

    def test_invalid_expected_scope(self):
        self.blocked("invalid_expected_scope", evidence=replace(self.evidence, expected_scope="project"))

    def test_expected_revision_required(self):
        self.blocked("invalid_expected_revision", evidence=replace(self.evidence, expected_revision=None))

    def test_bool_revision_invalid(self):
        self.blocked("invalid_expected_revision", evidence=replace(self.evidence, expected_revision=True))

    def test_missing_anchor(self):
        self.blocked("missing_or_invalid_anchor", anchor=None)

    def test_hostile_anchor_subclass(self):
        class Hostile(JournalAnchor):
            def __getattribute__(self, key):
                raise AssertionError(key)
        self.blocked("missing_or_invalid_anchor", anchor=Hostile(**self.anchor.__dict__))

    def test_hostile_protocol_member(self):
        class Hostile:
            def __eq__(self, other):
                raise AssertionError("Never compare untrusted objects")
            def __ne__(self, other):
                raise AssertionError("Never compare untrusted objects")
        self.blocked("unknown_anchor_protocol_or_flame_version", anchor=replace(self.anchor, protocol=Hostile()))

    def test_missing_key(self):
        self.blocked("invalid_trusted_key_material", key=None)

    def test_short_key(self):
        self.blocked("invalid_trusted_key_material", key=b"short")

    def test_too_long_key(self):
        self.blocked("invalid_trusted_key_material", key=b"x" * 65)

    def test_mutable_key_disallowed(self):
        self.blocked("invalid_trusted_key_material", key=bytearray(TEST_KEY))

    def test_mismatched_key_fails_mac(self):
        self.blocked("anchor_mac_mismatch", key=b"B" * 32)

    def test_modified_mac(self):
        self.blocked("anchor_mac_mismatch", anchor=replace(self.anchor, mac_sha256="f" * 64))

    def test_invalid_mac_encoding(self):
        self.blocked("invalid_anchor_digest_format", anchor=replace(self.anchor, mac_sha256="bad"))

    def test_modified_tip_without_mac(self):
        self.blocked("anchor_mac_mismatch", anchor=replace(self.anchor, tip_sha256="f" * 64))

    def test_wrong_protocol(self):
        self.blocked("unknown_anchor_protocol_or_flame_version", anchor=replace(self.anchor, protocol="legacy"))

    def test_wrong_flame_version(self):
        self.blocked("unknown_anchor_protocol_or_flame_version", anchor=replace(self.anchor, flame_version="2025.2.7"))

    def test_bad_scope(self):
        self.blocked("invalid_anchor_scope", anchor=replace(self.anchor, scope="application"))

    def test_key_id_substituted(self):
        self.blocked("anchor_identity_mismatch", anchor=replace(self.anchor, key_id="other"))

    def test_transaction_substituted(self):
        self.blocked("anchor_identity_mismatch", anchor=replace(self.anchor, transaction_id="other"))

    def test_scope_substituted(self):
        self.blocked("anchor_identity_mismatch", anchor=replace(self.anchor, scope="shared"))

    def test_invalid_anchor_identity(self):
        self.blocked("invalid_anchor_identity", anchor=replace(self.anchor, transaction_id="/private/shot"))

    def test_bad_terminal_state(self):
        self.blocked("invalid_anchor_terminal_state", anchor=replace(self.anchor, terminal_state="INTENT"))

    def test_wrong_event_count_for_state(self):
        self.blocked("invalid_anchor_revision_or_count", anchor=replace(self.anchor, event_count=5))

    def test_wrong_revision_for_state(self):
        self.blocked("invalid_anchor_revision_or_count", anchor=replace(self.anchor, revision=2))

    def test_validly_signed_but_old_revision(self):
        ev = replace(self.evidence, expected_revision=2)
        self.blocked("anchor_stale_revision", evidence=ev)

    def test_mismatched_event_count(self):
        self.blocked("anchor_event_count_mismatch", events=make_events(count=5))

    def test_malformed_event_collection(self):
        self.blocked("invalid_journal_event_collection", events=iter(self.events))

    def test_event_collection_not_read_if_mac_bad(self):
        class Exploding(list):
            def __len__(self):
                raise AssertionError("Events inspected before authenticating MAC")
            def __iter__(self):
                raise AssertionError("Events inspected before authenticating MAC")
        self.blocked("anchor_mac_mismatch", anchor=replace(self.anchor, mac_sha256="f" * 64), events=Exploding())

    def test_tampered_event_fails_chain_after_mac(self):
        events = [replace(self.events[0], payload_sha256="f" * 64), *self.events[1:]]
        self.blocked("journal_event_digest_mismatch", events=events)

    def test_signed_wrong_tip_fails_against_chain(self):
        a = sign_fixture(replace(self.anchor, tip_sha256="f" * 64))
        self.blocked("journal_tip_digest_mismatch", anchor=a)

    def test_signed_anchor_cannot_authenticate_malformed_events(self):
        events = [object(), *self.events[1:]]
        self.blocked("invalid_journal_event", events=events)

    def test_full_rewrite_and_new_anchor_works_if_key_compromised(self):
        # A compromised key+revision authority can sign a fabricated chain.
        events = make_events(count=3, tx="made-up")
        ev = replace(self.evidence, expected_transaction_id="made-up")
        signed = sign_fixture(replace(
            self.anchor, transaction_id="made-up", tip_sha256=events[-1].event_sha256))
        self.assertEqual(self.review(anchor=signed, evidence=ev, events=events).status, "PREVIEW_ONLY")

    def test_no_filesystem_io_even_on_valid_anchor(self):
        with patch.object(Path, "open", side_effect=AssertionError("no IO")), \
             patch.object(Path, "write_text", side_effect=AssertionError("no IO")), \
             patch.object(Path, "unlink", side_effect=AssertionError("no IO")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("no IO")):
            self.assertEqual(self.review().status, "PREVIEW_ONLY")

    def test_result_redacts_key_and_metadata(self):
        r = self.review(anchor=replace(self.anchor, mac_sha256="f" * 64))
        payload = repr(r)
        for secret in (self.anchor.key_id, self.anchor.transaction_id, self.anchor.mac_sha256, str(TEST_KEY)):
            self.assertNotIn(secret, payload)

    def test_no_sign_or_mutate_methods(self):
        self.assertFalse(hasattr(self.review(), "install"))
        self.assertFalse(hasattr(self.review(), "disable"))
        self.assertFalse(hasattr(self.review(), "sign"))


if __name__ == "__main__":
    unittest.main()
