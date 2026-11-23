"""Read-only, in-memory HMAC anchor review for disposable DGpy fixtures.

No key generation, persistence, logging, signing, Hook I/O or state changes.
The caller supplies a separately protected key and an independently reviewed
anchor/revision. A successful HMAC cannot establish key provenance, current
state, authorisation to modify a Hook, or protection from replay by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re

from .journal_review import JournalReview, JournalReviewEvidence, assess_journal_preview
from .preflight import Finding, VALIDATED_FLAME_VERSION


_ANCHOR_PROTOCOL = "DGpy-Hook-Anchor-v1"
_MAC_DOMAIN = b"DGpy Hook Anchor HMAC-SHA256 v1\n"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SCOPES = frozenset({"user", "shared"})
_FINALS = {"ACTIVE": (1, 3), "DISABLED": (2, 5)}


@dataclass(frozen=True)
class JournalAnchor:
    """Untrusted anchor metadata. No secret key or private file path here."""

    protocol: str
    flame_version: str
    scope: str
    key_id: str
    transaction_id: str
    revision: int
    event_count: int
    terminal_state: str
    tip_sha256: str
    mac_sha256: str


@dataclass(frozen=True)
class AnchorReviewEvidence:
    """External attestations; no field alone proves actual provenance."""

    key_origin_confirmed: bool = False
    anchor_origin_confirmed: bool = False
    isolated_environment_confirmed: bool = False
    expected_key_id: str | None = None
    expected_transaction_id: str | None = None
    expected_scope: str | None = None
    expected_revision: int | None = None


def _valid_id(value: object) -> bool:
    return type(value) is str and len(value) <= 64 and _ID.fullmatch(value) is not None


def _valid_digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and _DIGEST.fullmatch(value) is not None


def _blocked(code: str) -> JournalReview:
    return JournalReview((Finding(code),))


def assess_hmac_journal_preview(
    *,
    events: object,
    anchor: JournalAnchor | None,
    trusted_key: bytes | None,
    evidence: AnchorReviewEvidence = AnchorReviewEvidence(),
) -> JournalReview:
    """Match an externally keyed anchor to a bounded in-memory journal.

    Returns only BLOCKED or PREVIEW_ONLY. Even a matched MAC and chain are
    NOT proof that a real Hook is installed, safe to disable, or restorable.
    No source of keys, anchor storage or authenticated revision counter is
    implemented. Callers must never derive the trusted key from the journal.
    """
    # Refuse untrusted subclass getters and evaluate all claims before
    # reading any anchor, key or events. No filesystem access at any point.
    if type(evidence) is not AnchorReviewEvidence:
        return _blocked("invalid_anchor_evidence")
    if evidence.key_origin_confirmed is not True:
        return _blocked("trusted_key_origin_unconfirmed")
    if evidence.anchor_origin_confirmed is not True:
        return _blocked("anchor_origin_unconfirmed")
    if evidence.isolated_environment_confirmed is not True:
        return _blocked("isolated_environment_unconfirmed")
    if not _valid_id(evidence.expected_key_id):
        return _blocked("invalid_expected_key_id")
    if not _valid_id(evidence.expected_transaction_id):
        return _blocked("invalid_expected_transaction_id")
    if type(evidence.expected_scope) is not str or evidence.expected_scope not in _SCOPES:
        return _blocked("invalid_expected_scope")
    if type(evidence.expected_revision) is not int or evidence.expected_revision not in (1, 2):
        return _blocked("invalid_expected_revision")

    if type(anchor) is not JournalAnchor:
        return _blocked("missing_or_invalid_anchor")
    if type(trusted_key) is not bytes or not 32 <= len(trusted_key) <= 64:
        return _blocked("invalid_trusted_key_material")
    if (
        type(anchor.protocol) is not str
        or type(anchor.flame_version) is not str
        or anchor.protocol != _ANCHOR_PROTOCOL
        or anchor.flame_version != VALIDATED_FLAME_VERSION
    ):
        return _blocked("unknown_anchor_protocol_or_flame_version")
    if type(anchor.scope) is not str or anchor.scope not in _SCOPES:
        return _blocked("invalid_anchor_scope")
    if not _valid_id(anchor.key_id) or not _valid_id(anchor.transaction_id):
        return _blocked("invalid_anchor_identity")
    if (
        anchor.key_id != evidence.expected_key_id
        or anchor.transaction_id != evidence.expected_transaction_id
        or anchor.scope != evidence.expected_scope
    ):
        return _blocked("anchor_identity_mismatch")
    if type(anchor.terminal_state) is not str or anchor.terminal_state not in _FINALS:
        return _blocked("invalid_anchor_terminal_state")
    if (
        type(anchor.revision) is not int
        or type(anchor.event_count) is not int
        or (anchor.revision, anchor.event_count) != _FINALS[anchor.terminal_state]
    ):
        return _blocked("invalid_anchor_revision_or_count")
    if anchor.revision != evidence.expected_revision:
        return _blocked("anchor_stale_revision")
    if not _valid_digest(anchor.tip_sha256) or not _valid_digest(anchor.mac_sha256):
        return _blocked("invalid_anchor_digest_format")

    # Canonical, versioned, domain-separated bytes. No output contains a MAC,
    # key, transaction ID, user path or private project identifier.
    message = json.dumps(
        [_ANCHOR_PROTOCOL, anchor.flame_version, anchor.scope,
         anchor.key_id, anchor.transaction_id, anchor.revision,
         anchor.event_count, anchor.terminal_state, anchor.tip_sha256],
        ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")
    computed = hmac.new(trusted_key, _MAC_DOMAIN + message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, anchor.mac_sha256):
        return _blocked("anchor_mac_mismatch")

    # Only after passing an independently attested, keyed anchor may we
    # inspect the in-memory events. Their authenticity is still limited by
    # the externally supplied key's real confidentiality and provenance.
    if type(events) not in (list, tuple):
        return _blocked("invalid_journal_event_collection")
    if len(events) != anchor.event_count:
        return _blocked("anchor_event_count_mismatch")
    result = assess_journal_preview(
        events=events,
        evidence=JournalReviewEvidence(
            independent_tip_verified=True,
            isolated_environment_confirmed=True,
            expected_transaction_id=anchor.transaction_id,
            expected_tip_sha256=anchor.tip_sha256,
        ),
    )
    if result.status != "PREVIEW_ONLY":
        return result
    if result.terminal_state != anchor.terminal_state:
        return _blocked("anchor_terminal_state_mismatch")
    return result
