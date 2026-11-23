"""Experimental in-memory DGpy Hook v2 key-generation-bound HMAC preview.

This module does not load, generate, sign, store or rotate keys, does not
read/write journals, and never touches Flame, a Hook, or the filesystem.
Caller-provided attestations are NOT independently authenticated here.
A matching record is only PREVIEW_ONLY / NO_CHANGE, never authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re

from .journal_review import JournalReviewEvidence, assess_journal_preview
from .preflight import Finding, VALIDATED_FLAME_VERSION

_V2_PROTOCOL = "DGpy-Hook-Anchor-v2"
_KEY_PROTOCOL = "DGpy-Key-Custody-v2"
_V2_DOMAIN = b"DGpy Hook Anchor HMAC-SHA256 v2\n"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SCOPES = frozenset({"user", "shared"})
_TERMINALS = {"ACTIVE": (1, 3), "DISABLED": (2, 5)}
_KEY_STATES = frozenset({"ACTIVE", "RETIRED", "REVOKED"})
_MAX_GENERATION = 2**31 - 1


@dataclass(frozen=True)
class V2Anchor:
    """Untrusted metadata: generation is HMAC-bound in this protocol."""

    protocol: str
    flame_version: str
    scope: str
    transaction_id: str
    key_id: str
    key_generation: int
    revision: int
    event_count: int
    terminal_state: str
    tip_sha256: str
    mac_sha256: str


@dataclass(frozen=True)
class V2KeyState:
    """Untrusted snapshot; not an implementation of a key authority."""

    protocol: str
    flame_version: str
    scope: str
    transaction_id: str
    key_id: str
    generation: int
    lifecycle_state: str
    latest_revision: int
    latest_tip_sha256: str


@dataclass(frozen=True)
class V2Evidence:
    """External assertions that must be proven outside DGpy before use."""

    key_origin_verified: bool = False
    key_status_verified: bool = False
    checkpoint_origin_verified: bool = False
    anchor_origin_verified: bool = False
    isolated_environment_confirmed: bool = False
    expected_scope: str | None = None
    expected_transaction_id: str | None = None
    expected_key_id: str | None = None
    expected_generation: int | None = None
    expected_revision: int | None = None
    expected_tip_sha256: str | None = None


@dataclass(frozen=True)
class V2Review:
    """Sanitized, non-actionable finding. Never includes keys or IDs."""

    findings: tuple[Finding, ...]
    terminal_state: str | None = None

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"

    @property
    def next_step(self) -> str:
        return "MANUAL_RECONCILIATION" if self.findings else "NO_CHANGE"


def _stop(code: str) -> V2Review:
    return V2Review((Finding(code),))


def _valid_id(value: object) -> bool:
    return type(value) is str and len(value) <= 64 and _ID.fullmatch(value) is not None


def _valid_hash(value: object) -> bool:
    return type(value) is str and len(value) == 64 and _SHA256.fullmatch(value) is not None


def _valid_generation(value: object) -> bool:
    return type(value) is int and 1 <= value <= _MAX_GENERATION


def _valid_revision(value: object) -> bool:
    return type(value) is int and value in (1, 2)


def assess_v2_anchor_preview(
    *,
    evidence: V2Evidence = V2Evidence(),
    key_state: V2KeyState | None,
    anchor: V2Anchor | None,
    trusted_key: bytes | None,
    events: object,
) -> V2Review:
    """Review v2 HMAC + v1 journal-chain semantics, all in memory.

    Requires a separately protected, independent latest generation/revision/
    tip checkpoint, key state and key material. No actual trust provider,
    anti-replay authority, or key lifecycle is implemented in this function.
    """
    # Fail before accessing key_state/anchor/key/events if ANY independent
    # attestation or expected external identity is untrusted/malformed.
    if type(evidence) is not V2Evidence:
        return _stop("invalid_v2_evidence")
    if evidence.key_origin_verified is not True:
        return _stop("key_origin_unverified")
    if evidence.key_status_verified is not True:
        return _stop("key_status_unverified")
    if evidence.checkpoint_origin_verified is not True:
        return _stop("checkpoint_origin_unverified")
    if evidence.anchor_origin_verified is not True:
        return _stop("anchor_origin_unverified")
    if evidence.isolated_environment_confirmed is not True:
        return _stop("isolated_environment_unconfirmed")
    if type(evidence.expected_scope) is not str or evidence.expected_scope not in _SCOPES:
        return _stop("invalid_expected_scope")
    if not _valid_id(evidence.expected_transaction_id):
        return _stop("invalid_expected_transaction_id")
    if not _valid_id(evidence.expected_key_id):
        return _stop("invalid_expected_key_id")
    if not _valid_generation(evidence.expected_generation):
        return _stop("invalid_expected_generation")
    if not _valid_revision(evidence.expected_revision):
        return _stop("invalid_expected_revision")
    if not _valid_hash(evidence.expected_tip_sha256):
        return _stop("invalid_expected_tip")

    # Never use key-state data as its own proof of provenance or freshness.
    if type(key_state) is not V2KeyState:
        return _stop("missing_or_invalid_key_state")
    if (
        type(key_state.protocol) is not str
        or type(key_state.flame_version) is not str
        or key_state.protocol != _KEY_PROTOCOL
        or key_state.flame_version != VALIDATED_FLAME_VERSION
    ):
        return _stop("unsupported_key_state_version")
    if type(key_state.scope) is not str or key_state.scope not in _SCOPES:
        return _stop("invalid_key_state_scope")
    if not _valid_id(key_state.transaction_id) or not _valid_id(key_state.key_id):
        return _stop("invalid_key_state_identity")
    if not _valid_generation(key_state.generation):
        return _stop("invalid_key_state_generation")
    if type(key_state.lifecycle_state) is not str or key_state.lifecycle_state not in _KEY_STATES:
        return _stop("invalid_key_state_status")
    if key_state.lifecycle_state != "ACTIVE":
        return _stop("key_retired_or_revoked")
    if not _valid_revision(key_state.latest_revision) or not _valid_hash(key_state.latest_tip_sha256):
        return _stop("invalid_key_state_checkpoint")
    if (
        key_state.scope != evidence.expected_scope
        or key_state.transaction_id != evidence.expected_transaction_id
        or key_state.key_id != evidence.expected_key_id
        or key_state.generation != evidence.expected_generation
    ):
        return _stop("key_state_identity_mismatch")
    if (
        key_state.latest_revision != evidence.expected_revision
        or not hmac.compare_digest(key_state.latest_tip_sha256, evidence.expected_tip_sha256)
    ):
        return _stop("key_state_checkpoint_mismatch")

    # A signed v1 anchor MUST NOT be accepted by the v2 entry point.
    if type(anchor) is not V2Anchor:
        return _stop("missing_or_invalid_v2_anchor")
    if type(trusted_key) is not bytes or not 32 <= len(trusted_key) <= 64:
        return _stop("invalid_trusted_key")
    if (
        type(anchor.protocol) is not str
        or type(anchor.flame_version) is not str
        or anchor.protocol != _V2_PROTOCOL
        or anchor.flame_version != VALIDATED_FLAME_VERSION
    ):
        return _stop("unsupported_anchor_version")
    if type(anchor.scope) is not str or anchor.scope not in _SCOPES:
        return _stop("invalid_anchor_scope")
    if not _valid_id(anchor.transaction_id) or not _valid_id(anchor.key_id):
        return _stop("invalid_anchor_identity")
    if not _valid_generation(anchor.key_generation):
        return _stop("invalid_anchor_generation")
    if type(anchor.terminal_state) is not str or anchor.terminal_state not in _TERMINALS:
        return _stop("invalid_anchor_terminal_state")
    if (
        type(anchor.revision) is not int
        or type(anchor.event_count) is not int
        or (anchor.revision, anchor.event_count) != _TERMINALS[anchor.terminal_state]
    ):
        return _stop("invalid_anchor_revision_or_count")
    if not _valid_hash(anchor.tip_sha256) or not _valid_hash(anchor.mac_sha256):
        return _stop("invalid_anchor_digest")
    if (
        anchor.scope != evidence.expected_scope
        or anchor.transaction_id != evidence.expected_transaction_id
        or anchor.key_id != evidence.expected_key_id
        or anchor.key_generation != evidence.expected_generation
    ):
        return _stop("anchor_identity_mismatch")
    if (
        anchor.revision != evidence.expected_revision
        or not hmac.compare_digest(anchor.tip_sha256, evidence.expected_tip_sha256)
    ):
        return _stop("anchor_checkpoint_mismatch")

    # Explicit domain separation + fixed ordered canonical input. Generation
    # is included in the HMAC; unlike v1, generation substitution changes MAC.
    canonical = json.dumps(
        [_V2_PROTOCOL, anchor.flame_version, anchor.scope,
         anchor.transaction_id, anchor.key_id, anchor.key_generation,
         anchor.revision, anchor.event_count, anchor.terminal_state,
         anchor.tip_sha256],
        ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")
    digest = hmac.new(trusted_key, _V2_DOMAIN + canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, anchor.mac_sha256):
        return _stop("anchor_v2_mac_mismatch")

    # Inspect the in-memory journal only AFTER key status, external checkpoint,
    # metadata and HMAC checks pass. No v1 anchor downgrade or signing.
    if type(events) not in (tuple, list):
        return _stop("invalid_journal_collection")
    if len(events) != anchor.event_count:
        return _stop("journal_count_mismatch")
    result = assess_journal_preview(
        events=events,
        evidence=JournalReviewEvidence(
            independent_tip_verified=True,
            isolated_environment_confirmed=True,
            expected_transaction_id=evidence.expected_transaction_id,
            expected_tip_sha256=evidence.expected_tip_sha256,
        ),
    )
    if result.status != "PREVIEW_ONLY":
        return V2Review(result.findings)
    if result.terminal_state != anchor.terminal_state:
        return _stop("anchor_journal_terminal_mismatch")
    return V2Review((), result.terminal_state)
