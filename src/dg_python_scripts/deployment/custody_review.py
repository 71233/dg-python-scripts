"""Strict, in-memory key-custody and recovery gate for disposable fixtures.

This neither establishes trusted key custody nor authorizes changing a Hook.
It creates, reads, signs, stores, rotates, or revokes no keys or records.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .anchor_review import AnchorReviewEvidence, JournalAnchor, assess_hmac_journal_preview
from .journal_review import JournalReview
from .preflight import Finding, VALIDATED_FLAME_VERSION

_CUSTODY_PROTOCOL = "DGpy-Key-Custody-v1"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SCOPES = frozenset({"user", "shared"})
_KNOWN_STATES = frozenset({"ACTIVE", "RETIRED", "REVOKED"})


@dataclass(frozen=True)
class KeyCustodySnapshot:
    """Untrusted *metadata only*, supplied by a separate custody authority.

    Generation 1 is the only generation supported by the existing v1 HMAC
    anchor, which does NOT cryptographically include a generation number.
    Never reuse a key_id after rotation or revocation.
    """

    protocol: str
    flame_version: str
    scope: str
    transaction_id: str
    key_id: str
    generation: int
    state: str
    current_revision: int


@dataclass(frozen=True)
class CustodyReviewEvidence:
    """External attestations, NOT cryptographic or filesystem proofs."""

    custody_origin_verified: bool = False
    revocation_status_verified: bool = False
    latest_revision_verified: bool = False
    anchor_origin_verified: bool = False
    isolated_environment_confirmed: bool = False
    expected_scope: str | None = None
    expected_transaction_id: str | None = None
    expected_key_id: str | None = None
    expected_generation: int | None = None
    expected_revision: int | None = None


@dataclass(frozen=True)
class RecoveryPreview:
    """Non-actionable preview. There is no automatic recovery path."""

    findings: tuple[Finding, ...]
    terminal_state: str | None = None

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"

    @property
    def next_step(self) -> str:
        # In particular, no status means install, retry, unlink or restore.
        return "MANUAL_RECONCILIATION" if self.findings else "NO_CHANGE"


def _stop(code: str) -> RecoveryPreview:
    return RecoveryPreview((Finding(code),))


def _valid_id(value: object) -> bool:
    return type(value) is str and len(value) <= 64 and _ID.fullmatch(value) is not None


def assess_recovery_preview(
    *,
    custody: KeyCustodySnapshot | None,
    evidence: CustodyReviewEvidence = CustodyReviewEvidence(),
    anchor: JournalAnchor | None,
    trusted_key: bytes | None,
    events: object,
) -> RecoveryPreview:
    """Check external custody metadata before the existing v1 HMAC reviewer.

    A valid-looking record only confirms consistency *given* independent
    attestations. Key origin, revocation state, and monotonic revision must be
    verified by a separate trusted authority; this function cannot do that.
    Interrupted/replayed/mismatched histories always require human review.
    """
    # Do not touch custody, anchor, key, or events until the full external
    # trust boundary is attested; use exact classes to reject hostile getters.
    if type(evidence) is not CustodyReviewEvidence:
        return _stop("invalid_custody_evidence")
    if evidence.custody_origin_verified is not True:
        return _stop("custody_origin_unverified")
    if evidence.revocation_status_verified is not True:
        return _stop("revocation_status_unverified")
    if evidence.latest_revision_verified is not True:
        return _stop("latest_revision_unverified")
    if evidence.anchor_origin_verified is not True:
        return _stop("anchor_origin_unverified")
    if evidence.isolated_environment_confirmed is not True:
        return _stop("isolated_environment_unconfirmed")
    if type(evidence.expected_scope) is not str or evidence.expected_scope not in _SCOPES:
        return _stop("invalid_expected_scope")
    if not _valid_id(evidence.expected_key_id):
        return _stop("invalid_expected_key_id")
    if not _valid_id(evidence.expected_transaction_id):
        return _stop("invalid_expected_transaction_id")
    if type(evidence.expected_generation) is not int or evidence.expected_generation != 1:
        return _stop("unsupported_expected_key_generation")
    if type(evidence.expected_revision) is not int or evidence.expected_revision not in (1, 2):
        return _stop("invalid_expected_revision")

    if type(custody) is not KeyCustodySnapshot:
        return _stop("missing_or_invalid_custody_snapshot")
    if (
        type(custody.protocol) is not str
        or type(custody.flame_version) is not str
        or custody.protocol != _CUSTODY_PROTOCOL
        or custody.flame_version != VALIDATED_FLAME_VERSION
    ):
        return _stop("unknown_custody_protocol_or_flame_version")
    if type(custody.scope) is not str or custody.scope not in _SCOPES:
        return _stop("invalid_custody_scope")
    if not _valid_id(custody.key_id) or not _valid_id(custody.transaction_id):
        return _stop("invalid_custody_identity")
    if type(custody.generation) is not int or custody.generation != 1:
        # Anchor v1 does not bind generation. Block ALL later generations.
        return _stop("key_rotation_requires_new_protocol")
    if type(custody.state) is not str or custody.state not in _KNOWN_STATES:
        return _stop("invalid_key_lifecycle_state")
    if custody.state != "ACTIVE":
        return _stop("key_retired_or_revoked")
    if type(custody.current_revision) is not int or custody.current_revision not in (1, 2):
        return _stop("invalid_custody_revision")
    if (
        custody.scope != evidence.expected_scope
        or custody.key_id != evidence.expected_key_id
        or custody.transaction_id != evidence.expected_transaction_id
        or custody.generation != evidence.expected_generation
    ):
        return _stop("custody_identity_mismatch")
    if custody.current_revision != evidence.expected_revision:
        return _stop("custody_revision_mismatch")

    # Do NOT infer trust from the custody record itself. Derive the anchor's
    # expected identity from independently attested, already validated fields.
    # No journaling, reading, signing, or mutation is implemented here.
    checked: JournalReview = assess_hmac_journal_preview(
        events=events,
        anchor=anchor,
        trusted_key=trusted_key,
        evidence=AnchorReviewEvidence(
            key_origin_confirmed=True,
            anchor_origin_confirmed=True,
            isolated_environment_confirmed=True,
            expected_key_id=evidence.expected_key_id,
            expected_transaction_id=evidence.expected_transaction_id,
            expected_scope=evidence.expected_scope,
            expected_revision=evidence.expected_revision,
        ),
    )
    if type(checked) is not JournalReview:
        return _stop("invalid_anchor_review_result")
    if checked.findings:
        return RecoveryPreview(checked.findings)
    expected_state = "ACTIVE" if evidence.expected_revision == 1 else "DISABLED"
    if checked.terminal_state != expected_state:
        return _stop("custody_anchor_terminal_mismatch")
    return RecoveryPreview((), checked.terminal_state)
