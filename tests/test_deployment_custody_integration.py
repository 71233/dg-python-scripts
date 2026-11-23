"""End-to-end in-memory custody -> HMAC -> journal fixture checks.

Only public deterministic fixture keys are used; no Hook or filesystem I/O.
"""

from dataclasses import replace
import hashlib
import hmac
import json
import unittest

from dg_python_scripts.deployment.anchor_review import JournalAnchor
from dg_python_scripts.deployment.custody_review import (
    CustodyReviewEvidence, KeyCustodySnapshot, assess_recovery_preview,
)
from dg_python_scripts.deployment.journal_review import JournalEvent

KEY = bytes(range(32))  # Public deterministic test bytes, not a secret.
ORDER = ("INTENT", "LINK_CREATED", "ACTIVE", "DISABLE_INTENT", "DISABLED")


def fixture(count=3, scope="user", tx="fixture-tx"):
    previous = "0" * 64
    events = []
    for sequence in range(count):
        payload = hashlib.sha256(("mock-payload:%d" % sequence).encode()).hexdigest()
        event_fields = [sequence, tx, ORDER[sequence], payload, previous]
        digest = hashlib.sha256(
            b"DGpy Hook Journal v1\n" + json.dumps(
                event_fields, ensure_ascii=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest()
        events.append(JournalEvent(*event_fields, digest))
        previous = digest
    revision = 1 if count == 3 else 2
    state = "ACTIVE" if revision == 1 else "DISABLED"
    anchor = JournalAnchor(
        protocol="DGpy-Hook-Anchor-v1", flame_version="2026.2.3",
        scope=scope, key_id="fixture-key", transaction_id=tx,
        revision=revision, event_count=count, terminal_state=state,
        tip_sha256=previous, mac_sha256="0" * 64,
    )
    anchor_fields = [
        anchor.protocol, anchor.flame_version, anchor.scope, anchor.key_id,
        anchor.transaction_id, anchor.revision, anchor.event_count,
        anchor.terminal_state, anchor.tip_sha256,
    ]
    mac = hmac.new(KEY, b"DGpy Hook Anchor HMAC-SHA256 v1\n" + json.dumps(
        anchor_fields, ensure_ascii=True, separators=(",", ":")
    ).encode("ascii"), hashlib.sha256).hexdigest()
    anchor = replace(anchor, mac_sha256=mac)
    custody = KeyCustodySnapshot(
        "DGpy-Key-Custody-v1", "2026.2.3", scope, tx,
        "fixture-key", 1, "ACTIVE", revision,
    )
    evidence = CustodyReviewEvidence(
        custody_origin_verified=True, revocation_status_verified=True,
        latest_revision_verified=True, anchor_origin_verified=True,
        isolated_environment_confirmed=True, expected_scope=scope,
        expected_transaction_id=tx, expected_key_id="fixture-key",
        expected_generation=1, expected_revision=revision,
    )
    return events, anchor, custody, evidence


class CustodyIntegrationTests(unittest.TestCase):
    def report(self, events, anchor, custody, evidence, key=KEY):
        return assess_recovery_preview(
            events=events, anchor=anchor, custody=custody,
            evidence=evidence, trusted_key=key,
        )

    def test_signed_active_chain_only_previews(self):
        args = fixture()
        r = self.report(*args)
        self.assertEqual((r.status, r.terminal_state, r.next_step),
                         ("PREVIEW_ONLY", "ACTIVE", "NO_CHANGE"))

    def test_signed_disabled_chain_only_previews(self):
        args = fixture(5)
        r = self.report(*args)
        self.assertEqual((r.status, r.terminal_state, r.next_step),
                         ("PREVIEW_ONLY", "DISABLED", "NO_CHANGE"))

    def test_shared_scope_has_separate_binding(self):
        args = fixture(3, "shared")
        self.assertEqual(self.report(*args).status, "PREVIEW_ONLY")

    def test_wrong_key_blocks_and_requires_manual_review(self):
        args = fixture()
        r = self.report(*args, key=b"W" * 32)
        self.assertEqual(r.status, "BLOCKED")
        self.assertEqual(r.next_step, "MANUAL_RECONCILIATION")
        self.assertIn("anchor_mac_mismatch", [x.code for x in r.findings])

    def test_incomplete_history_never_autoretries(self):
        events, anchor, custody, evidence = fixture()
        r = self.report(events[:2], anchor, custody, evidence)
        self.assertEqual(r.status, "BLOCKED")
        self.assertEqual(r.next_step, "MANUAL_RECONCILIATION")
        self.assertIn("anchor_event_count_mismatch", [x.code for x in r.findings])
        self.assertFalse(hasattr(r, "retry"))

    def test_tampered_event_digest_blocks(self):
        events, anchor, custody, evidence = fixture()
        events[0] = replace(events[0], payload_sha256="f" * 64)
        r = self.report(events, anchor, custody, evidence)
        self.assertEqual(r.status, "BLOCKED")
        self.assertIn("journal_event_digest_mismatch", [x.code for x in r.findings])

    def test_old_valid_anchor_blocked_by_current_revision(self):
        events, anchor, custody, evidence = fixture(3)
        custody = replace(custody, current_revision=2)
        evidence = replace(evidence, expected_revision=2)
        r = self.report(events, anchor, custody, evidence)
        self.assertEqual(r.status, "BLOCKED")
        self.assertIn("anchor_stale_revision", [x.code for x in r.findings])

    def test_revoked_key_blocks_even_correct_hmac(self):
        events, anchor, custody, evidence = fixture()
        r = self.report(events, anchor, replace(custody, state="REVOKED"), evidence)
        self.assertEqual(r.status, "BLOCKED")
        self.assertIn("key_retired_or_revoked", [x.code for x in r.findings])

    def test_rotated_key_requires_future_protocol(self):
        events, anchor, custody, evidence = fixture()
        r = self.report(events, anchor, replace(custody, generation=2), evidence)
        self.assertEqual(r.status, "BLOCKED")
        self.assertIn("key_rotation_requires_new_protocol", [x.code for x in r.findings])


if __name__ == "__main__":
    unittest.main()
