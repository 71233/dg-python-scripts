"""Pure, read-only review of an externally anchored DGpy Hook journal chain.

No journal is opened, created, signed, authenticated, saved, or executed here.
The caller must independently authenticate the expected digest (tip) and
transaction identity. A matched hash chain is NOT authorization to mutate a
Hook: a complete attacker-controlled chain can be recomputed by an attacker.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re

from .preflight import Finding


_JOURNAL_DOMAIN = b"DGpy Hook Journal v1\n"
_GENESIS_SHA256 = "0" * 64
_MAX_EVENTS = 5
_TRANSACTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EVENT_ORDER = (
    "INTENT",
    "LINK_CREATED",
    "ACTIVE",
    "DISABLE_INTENT",
    "DISABLED",
)
_TERMINAL_STATES = frozenset({"ACTIVE", "DISABLED"})


@dataclass(frozen=True)
class JournalEvent:
    """Only generic metadata; never place paths, user data or secrets here.

    payload_sha256 refers to separately held private evidence. This code
    does not validate that evidence's content or authenticity.
    """

    sequence: int
    transaction_id: str
    event_type: str
    payload_sha256: str
    previous_sha256: str
    event_sha256: str


@dataclass(frozen=True)
class JournalReviewEvidence:
    """External operator claims, not cryptographic authentication by DGpy."""

    independent_tip_verified: bool = False
    isolated_environment_confirmed: bool = False
    expected_transaction_id: str | None = None
    expected_tip_sha256: str | None = None


@dataclass(frozen=True)
class JournalReview:
    """An intentionally non-actionable, sanitized review result."""

    findings: tuple[Finding, ...]
    terminal_state: str | None = None

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"


def _valid_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _valid_tx_id(value: object) -> bool:
    return type(value) is str and _TRANSACTION_ID.fullmatch(value) is not None


def _digest(event: JournalEvent) -> str:
    """Domain-separated, deterministic digest of the six public event fields.

    The digest itself is excluded from the digest input. Never confuse this
    unkeyed hash with a signature or MAC, or trust a tip from the same journal.
    """
    serialized = json.dumps(
        [event.sequence, event.transaction_id, event.event_type,
         event.payload_sha256, event.previous_sha256],
        ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(_JOURNAL_DOMAIN + serialized).hexdigest()


def assess_journal_preview(
    *,
    events: list[JournalEvent] | tuple[JournalEvent, ...] | None,
    evidence: JournalReviewEvidence = JournalReviewEvidence(),
) -> JournalReview:
    """Check a bounded in-memory journal chain; never read or write files.

    PREVIEW_ONLY only means the chain and externally supplied tip matched this
    model. No certificate, key, journal trust, disk state, or install/disable
    permission is established here. Interrupted transactions always BLOCK.
    """
    def blocked(code: str) -> JournalReview:
        return JournalReview((Finding(code),))

    if type(evidence) is not JournalReviewEvidence:
        return blocked("invalid_journal_evidence")
    if evidence.independent_tip_verified is not True:
        return blocked("trusted_tip_unconfirmed")
    if evidence.isolated_environment_confirmed is not True:
        return blocked("isolated_environment_unconfirmed")
    if not _valid_tx_id(evidence.expected_transaction_id):
        return blocked("invalid_expected_transaction_id")
    if not _valid_sha256(evidence.expected_tip_sha256):
        return blocked("invalid_expected_tip_digest")

    # Refuse unbounded iterators, customized containers, and even one excess
    # event. The current v1 state machine supports exactly one Bootstrap.
    if type(events) not in (list, tuple):
        return blocked("invalid_journal_event_collection")
    if not events:
        return blocked("journal_events_missing")
    if len(events) > _MAX_EVENTS:
        return blocked("journal_too_many_events")

    previous = _GENESIS_SHA256
    last_state: str | None = None
    for i, event in enumerate(tuple(events)):
        if type(event) is not JournalEvent:
            return blocked("invalid_journal_event")
        if type(event.sequence) is not int or event.sequence != i:
            return blocked("journal_sequence_mismatch")
        if not _valid_tx_id(event.transaction_id):
            return blocked("invalid_event_transaction_id")
        if event.transaction_id != evidence.expected_transaction_id:
            return blocked("journal_transaction_changed")
        if type(event.event_type) is not str or event.event_type != _EVENT_ORDER[i]:
            return blocked("invalid_journal_transition")
        if (
            not _valid_sha256(event.payload_sha256)
            or not _valid_sha256(event.previous_sha256)
            or not _valid_sha256(event.event_sha256)
        ):
            return blocked("invalid_event_digest_format")
        if not hmac.compare_digest(event.previous_sha256, previous):
            return blocked("journal_chain_broken")
        calculated = _digest(event)
        if not hmac.compare_digest(event.event_sha256, calculated):
            return blocked("journal_event_digest_mismatch")
        previous = calculated
        last_state = event.event_type

    if not hmac.compare_digest(previous, evidence.expected_tip_sha256):
        return blocked("journal_tip_digest_mismatch")
    if last_state not in _TERMINAL_STATES:
        return blocked("journal_incomplete_transaction")
    return JournalReview((), last_state)
