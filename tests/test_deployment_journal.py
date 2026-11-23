"""Pure memory-only journal chain review. No Flame or Hook disk operations."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from dg_python_scripts.deployment import (
    JournalEvent, JournalReviewEvidence, assess_journal_preview,
)

DOMAIN = b"DGpy Hook Journal v1\n"
KINDS = ("INTENT", "LINK_CREATED", "ACTIVE", "DISABLE_INTENT", "DISABLED")


def make_events(count=3, tx="test-transaction"):
    events = []
    previous = "0" * 64
    for i, kind in enumerate(KINDS[:count]):
        payload = hashlib.sha256(("fixture-payload-%d" % i).encode("ascii")).hexdigest()
        digest = hashlib.sha256(DOMAIN + json.dumps(
            [i, tx, kind, payload, previous], ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")).hexdigest()
        event = JournalEvent(i, tx, kind, payload, previous, digest)
        events.append(event)
        previous = digest
    return events


class JournalReviewTests(unittest.TestCase):
    def setUp(self):
        self.events = make_events()
        self.evidence = JournalReviewEvidence(
            independent_tip_verified=True,
            isolated_environment_confirmed=True,
            expected_transaction_id="test-transaction",
            expected_tip_sha256=self.events[-1].event_sha256,
        )

    def report(self, events=None, evidence=None):
        return assess_journal_preview(
            events=self.events if events is None else events,
            evidence=self.evidence if evidence is None else evidence,
        )

    def assert_blocked(self, code, events=None, evidence=None):
        r = self.report(events, evidence)
        self.assertEqual(r.status, "BLOCKED")
        self.assertIn(code, [f.code for f in r.findings])
        self.assertIsNone(r.terminal_state)

    def test_complete_active_chain_is_only_preview(self):
        result = self.report()
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertEqual(result.terminal_state, "ACTIVE")
        self.assertFalse(hasattr(result, "apply"))

    def test_complete_disabled_chain_is_only_preview(self):
        events = make_events(5)
        proof = replace(self.evidence, expected_tip_sha256=events[-1].event_sha256)
        result = self.report(events, proof)
        self.assertEqual(result.status, "PREVIEW_ONLY")
        self.assertEqual(result.terminal_state, "DISABLED")
        self.assertFalse(hasattr(result, "restore"))

    def test_default_evidence_blocks(self):
        self.assert_blocked("trusted_tip_unconfirmed", evidence=JournalReviewEvidence())

    def test_unknown_isolation_blocks(self):
        ev = replace(self.evidence, isolated_environment_confirmed=False)
        self.assert_blocked("isolated_environment_unconfirmed", evidence=ev)

    def test_truthy_string_does_not_authenticate(self):
        ev = replace(self.evidence, independent_tip_verified="yes")
        self.assert_blocked("trusted_tip_unconfirmed", evidence=ev)

    def test_invalid_evidence_object_blocks(self):
        self.assert_blocked("invalid_journal_evidence", evidence={})

    def test_custom_evidence_subclass_is_not_inspected(self):
        class HostileEvidence(JournalReviewEvidence):
            def __getattribute__(self, key):
                raise AssertionError("Do not access untrusted subclass")
        result = self.report(evidence=HostileEvidence())
        self.assertEqual([x.code for x in result.findings], ["invalid_journal_evidence"])

    def test_custom_event_subclass_is_not_inspected(self):
        class HostileEvent(JournalEvent):
            def __getattribute__(self, key):
                raise AssertionError("Do not access untrusted subclass")
        initial = self.events[0]
        injected = HostileEvent(*(
            initial.sequence, initial.transaction_id, initial.event_type,
            initial.payload_sha256, initial.previous_sha256, initial.event_sha256,
        ))
        self.assert_blocked("invalid_journal_event", events=[injected, *self.events[1:]])

    def test_digest_subclass_rejected(self):
        class DigestSubclass(str):
            pass
        ev = replace(self.evidence, expected_tip_sha256=DigestSubclass(self.evidence.expected_tip_sha256))
        self.assert_blocked("invalid_expected_tip_digest", evidence=ev)

    def test_transaction_subclass_rejected(self):
        class IdSubclass(str):
            pass
        ev = replace(self.evidence, expected_transaction_id=IdSubclass("test-transaction"))
        self.assert_blocked("invalid_expected_transaction_id", evidence=ev)

    def test_no_event_access_when_evidence_untrusted(self):
        class ExplodingList(list):
            def __iter__(self):
                raise AssertionError("Should not touch events")
            def __len__(self):
                raise AssertionError("Should not touch events")
        result = self.report(ExplodingList(), JournalReviewEvidence())
        self.assertEqual(result.status, "BLOCKED")

    def test_expected_id_missing(self):
        self.assert_blocked("invalid_expected_transaction_id", evidence=replace(self.evidence, expected_transaction_id=None))

    def test_expected_id_contains_private_path(self):
        self.assert_blocked("invalid_expected_transaction_id", evidence=replace(self.evidence, expected_transaction_id="/private/project"))

    def test_expected_digest_invalid(self):
        self.assert_blocked("invalid_expected_tip_digest", evidence=replace(self.evidence, expected_tip_sha256="not-a-digest"))

    def test_expected_digest_uppercase_rejected(self):
        self.assert_blocked("invalid_expected_tip_digest", evidence=replace(self.evidence, expected_tip_sha256=self.evidence.expected_tip_sha256.upper()))

    def test_empty_journal_blocks(self):
        self.assert_blocked("journal_events_missing", events=[])

    def test_none_journal_blocks(self):
        result = assess_journal_preview(events=None, evidence=self.evidence)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual([x.code for x in result.findings], ["invalid_journal_event_collection"])

    def test_non_sequence_iterator_blocks(self):
        self.assert_blocked("invalid_journal_event_collection", events=iter(self.events))

    def test_string_events_blocks(self):
        self.assert_blocked("invalid_journal_event_collection", events="events")

    def test_too_many_events_blocks(self):
        self.assert_blocked("journal_too_many_events", events=self.events * 30)

    def test_wrong_event_type_blocks(self):
        events = [None, *self.events[1:]]
        self.assert_blocked("invalid_journal_event", events=events)

    def test_bool_index_blocks(self):
        events = [replace(self.events[0], sequence=False), *self.events[1:]]
        self.assert_blocked("journal_sequence_mismatch", events=events)

    def test_skip_sequence_blocks(self):
        events = [self.events[0], replace(self.events[1], sequence=4), self.events[2]]
        self.assert_blocked("journal_sequence_mismatch", events=events)

    def test_same_id_required(self):
        events = [self.events[0], replace(self.events[1], transaction_id="other"), self.events[2]]
        self.assert_blocked("journal_transaction_changed", events=events)

    def test_malformed_event_id_blocks(self):
        events = [replace(self.events[0], transaction_id="private/user"), *self.events[1:]]
        self.assert_blocked("invalid_event_transaction_id", events=events)

    def test_unexpected_initial_event_blocks(self):
        events = [replace(self.events[0], event_type="ACTIVE"), *self.events[1:]]
        self.assert_blocked("invalid_journal_transition", events=events)

    def test_repeated_active_event_blocks(self):
        events = [*self.events, replace(self.events[-1], sequence=3)]
        self.assert_blocked("invalid_journal_transition", events=events)

    def test_disabling_without_intent_blocks(self):
        events = [*self.events, replace(self.events[-1], sequence=3, event_type="DISABLED")]
        self.assert_blocked("invalid_journal_transition", events=events)

    def test_changed_payload_blocks(self):
        events = [replace(self.events[0], payload_sha256="f" * 64), *self.events[1:]]
        self.assert_blocked("journal_event_digest_mismatch", events=events)

    def test_invalid_payload_digest_blocks(self):
        events = [replace(self.events[0], payload_sha256="invalid"), *self.events[1:]]
        self.assert_blocked("invalid_event_digest_format", events=events)

    def test_modified_previous_digest_blocks(self):
        events = [self.events[0], replace(self.events[1], previous_sha256="f" * 64), self.events[2]]
        self.assert_blocked("journal_chain_broken", events=events)

    def test_changed_event_digest_blocks(self):
        events = [replace(self.events[0], event_sha256="f" * 64), *self.events[1:]]
        self.assert_blocked("journal_event_digest_mismatch", events=events)

    def test_missing_first_event_blocks(self):
        events = self.events[1:]
        self.assert_blocked("journal_sequence_mismatch", events=events)

    def test_wrong_tip_digest_blocks(self):
        ev = replace(self.evidence, expected_tip_sha256="f" * 64)
        self.assert_blocked("journal_tip_digest_mismatch", evidence=ev)

    def test_pending_intent_blocks(self):
        events = make_events(1)
        ev = replace(self.evidence, expected_tip_sha256=events[-1].event_sha256)
        self.assert_blocked("journal_incomplete_transaction", events=events, evidence=ev)

    def test_pending_link_created_blocks(self):
        events = make_events(2)
        ev = replace(self.evidence, expected_tip_sha256=events[-1].event_sha256)
        self.assert_blocked("journal_incomplete_transaction", events=events, evidence=ev)

    def test_pending_disable_intent_blocks(self):
        events = make_events(4)
        ev = replace(self.evidence, expected_tip_sha256=events[-1].event_sha256)
        self.assert_blocked("journal_incomplete_transaction", events=events, evidence=ev)

    def test_rewrite_chain_with_stale_anchor_blocks(self):
        # A chain can always be recomputed; only an independently secured
        # anchor makes the rewrite detectable here.
        events = make_events(3, tx="replacement")
        ev = replace(self.evidence, expected_transaction_id="replacement")
        self.assert_blocked("journal_tip_digest_mismatch", events=events, evidence=ev)

    def test_fully_rewritten_and_reanchored_chain_can_appear_consistent(self):
        # An unkeyed hash is not authentication. This documents why a tip
        # must come from outside any attacker-controlled journal.
        events = make_events(3, tx="replacement")
        ev = replace(self.evidence, expected_transaction_id="replacement",
                     expected_tip_sha256=events[-1].event_sha256)
        self.assertEqual(self.report(events=events, evidence=ev).status, "PREVIEW_ONLY")

    def test_event_digest_is_case_sensitive(self):
        events = [replace(self.events[0], event_sha256=self.events[0].event_sha256.upper()), *self.events[1:]]
        self.assert_blocked("invalid_event_digest_format", events=events)

    def test_result_hides_sensitive_metadata(self):
        ev = replace(self.evidence, expected_transaction_id="private/project")
        report = self.report(evidence=ev)
        self.assertNotIn("private/project", repr(report))
        self.assertNotIn(self.events[0].event_sha256, repr(report))

    def test_no_path_or_write_apis_needed(self):
        with patch.object(Path, "open", side_effect=AssertionError("no open")), \
             patch.object(Path, "write_text", side_effect=AssertionError("no write")), \
             patch.object(Path, "unlink", side_effect=AssertionError("no unlink")):
            self.assertEqual(self.report().status, "PREVIEW_ONLY")

    def test_tuple_input_supported(self):
        result = self.report(tuple(self.events))
        self.assertEqual(result.status, "PREVIEW_ONLY")


if __name__ == "__main__":
    unittest.main()
