"""Read-only comparison of separately supplied Flame Hook context snapshots.

No Flame import, filesystem reads, credentials, Hook installation or recovery.
An attested in-memory match is NOT proof of actual loader state or authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import stat

from .preflight import (
    BOOTSTRAP_NAME, Finding, INSTALL_TARGET_SCOPES,
    STANDARD_SCOPES, VALIDATED_FLAME_VERSION,
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_OPTIONAL_ABSENT = frozenset({"user", "project"})
_MAX_ROOTS = 24


@dataclass(frozen=True)
class RootSnapshot:
    """Private input only. Metadata must be collected and attested elsewhere."""
    scope: str
    path: str
    present: bool
    device: int | None = None
    inode: int | None = None
    owner_uid: int | None = None
    mode: int | None = None


@dataclass(frozen=True)
class HookContextRecord:
    """Candidate identity binding or independently observed session context.

    Root tuple order is significant: different Hook search order blocks.
    Paths never appear in findings, logs, returned hashes or identifiers.
    """
    deployment_id: str
    flame_version: str
    target_scope: str
    destination: str
    source: str
    source_revision: str
    source_sha256: str
    roots: tuple[RootSnapshot, ...]


@dataclass(frozen=True)
class HookContextEvidence:
    """External attestations, not automatically established by this code."""
    binding_origin_verified: bool = False
    live_roots_verified: bool = False
    additional_paths_verified: bool = False
    effective_sysconfig_verified: bool = False
    shared_failover_state_verified: bool = False
    project_context_verified: bool = False
    root_metadata_verified: bool = False
    source_revision_verified: bool = False
    isolated_environment_confirmed: bool = False
    expected_deployment_id: str | None = None
    expected_target_scope: str | None = None


@dataclass(frozen=True)
class HookContextReview:
    """Sanitized, non-actionable preview that never exposes host paths."""
    findings: tuple[Finding, ...]

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"

    @property
    def next_step(self) -> str:
        return "MANUAL_RECONCILIATION" if self.findings else "NO_CHANGE"


def _stop(code: str) -> HookContextReview:
    return HookContextReview((Finding(code),))


def _id(value: object) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None


def _hash(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _path(value: object) -> bool:
    """Only syntactic POSIX normalization; does NOT resolve symlinks."""
    if type(value) is not str or len(value) < 2 or len(value) > 1024:
        return False
    if not value.startswith("/") or value.startswith("//") or "\x00" in value:
        return False
    parts = value.split("/")
    return all(part not in ("", ".", "..") and not any(ord(c) < 32 for c in part)
               for part in parts[1:])


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def _root_code(roots: object, target: str, source: str, destination: str) -> str | None:
    if type(roots) is not tuple or not 4 <= len(roots) <= _MAX_ROOTS:
        return "invalid_hook_roots_collection"
    seen_scopes: set[str] = set()
    seen_paths: set[str] = set()
    identities: set[tuple[int, int]] = set()
    seen_ancestors: list[str] = []
    selected: RootSnapshot | None = None
    for root in roots:
        if type(root) is not RootSnapshot:
            return "invalid_root_snapshot"
        if type(root.scope) is not str or root.scope not in STANDARD_SCOPES | {"extra"}:
            return "invalid_root_scope"
        if root.scope in STANDARD_SCOPES:
            if root.scope in seen_scopes:
                return "duplicate_standard_scope"
            seen_scopes.add(root.scope)
        if not _path(root.path):
            return "invalid_root_path"
        folded = root.path.casefold()
        if folded in seen_paths:
            return "duplicate_root_path"
        for previous in seen_ancestors:
            if _inside(folded, previous) or _inside(previous, folded):
                return "overlapping_hook_roots"
        seen_paths.add(folded)
        seen_ancestors.append(folded)
        if type(root.present) is not bool:
            return "invalid_root_presence"
        if root.present:
            fields = (root.device, root.inode, root.owner_uid, root.mode)
            if any(type(n) is not int or n < 0 for n in fields):
                return "invalid_root_identity"
            if root.device == 0 or root.inode == 0 or not stat.S_ISDIR(root.mode):
                return "invalid_root_directory_identity"
            identity = (root.device, root.inode)
            if identity in identities:
                return "duplicate_root_identity"
            identities.add(identity)
            if root.mode & stat.S_IWOTH:
                return "world_writable_hook_root"
        else:
            if any(v is not None for v in (root.device, root.inode, root.owner_uid, root.mode)):
                return "absent_root_has_identity"
            if root.scope not in _OPTIONAL_ABSENT or root.scope == target:
                return "required_hook_root_absent"
        if root.scope == target:
            selected = root
        if _inside(source.casefold(), folded):
            return "source_inside_hook_root"
    if seen_scopes != STANDARD_SCOPES:
        return "missing_standard_hook_scope"
    if selected is None or not selected.present:
        return "target_root_unavailable"
    if destination != selected.path + "/" + BOOTSTRAP_NAME:
        return "destination_not_selected_bootstrap"
    return None


def _record_code(record: object) -> str | None:
    if type(record) is not HookContextRecord:
        return "missing_or_invalid_hook_context"
    if not _id(record.deployment_id):
        return "invalid_deployment_id"
    if type(record.flame_version) is not str or record.flame_version != VALIDATED_FLAME_VERSION:
        return "unvalidated_flame_version"
    if type(record.target_scope) is not str or record.target_scope not in INSTALL_TARGET_SCOPES:
        return "unsupported_target_scope"
    if not _path(record.destination) or not _path(record.source):
        return "invalid_context_paths"
    if record.source == record.destination or not record.source.endswith("/" + BOOTSTRAP_NAME):
        return "invalid_source_location"
    if type(record.source_revision) is not str or _REVISION.fullmatch(record.source_revision) is None:
        return "invalid_source_revision"
    if not _hash(record.source_sha256):
        return "invalid_source_digest"
    return _root_code(record.roots, record.target_scope, record.source, record.destination)


def assess_hook_context_preview(
    *,
    binding: HookContextRecord | None,
    observed: HookContextRecord | None,
    evidence: HookContextEvidence = HookContextEvidence(),
) -> HookContextReview:
    """Compare private in-memory binding and observed search-root snapshots.

    No direct filesystem access; external attestation of the actual Flame
    session, symlinks, ACL/mount and storage failover is mandatory but NOT
    proven by a True flag. PREVIEW_ONLY never authorizes Hook mutation.
    """
    if type(evidence) is not HookContextEvidence:
        return _stop("invalid_context_evidence")
    fields = (
        ("binding_origin_verified", "binding_origin_unverified"),
        ("live_roots_verified", "effective_roots_unverified"),
        ("additional_paths_verified", "additional_paths_unverified"),
        ("effective_sysconfig_verified", "sysconfig_resolution_unverified"),
        ("shared_failover_state_verified", "shared_failover_state_unverified"),
        ("project_context_verified", "project_context_unverified"),
        ("root_metadata_verified", "root_metadata_unverified"),
        ("source_revision_verified", "source_revision_unverified"),
        ("isolated_environment_confirmed", "isolated_environment_unconfirmed"),
    )
    for attr, code in fields:
        if getattr(evidence, attr) is not True:
            return _stop(code)
    if not _id(evidence.expected_deployment_id):
        return _stop("invalid_expected_deployment_id")
    if type(evidence.expected_target_scope) is not str or evidence.expected_target_scope not in INSTALL_TARGET_SCOPES:
        return _stop("invalid_expected_target_scope")
    for record, code in ((binding, "invalid_binding"), (observed, "invalid_observation")):
        result = _record_code(record)
        if result is not None:
            return _stop(code + "_" + result)
    if binding.deployment_id != evidence.expected_deployment_id:
        return _stop("binding_deployment_id_mismatch")
    if observed.deployment_id != evidence.expected_deployment_id:
        return _stop("observed_deployment_id_mismatch")
    if (binding.target_scope != evidence.expected_target_scope or
            observed.target_scope != evidence.expected_target_scope):
        return _stop("target_scope_mismatch")
    if binding != observed:
        # Full ordered root tuple, paths, device/inode/UID/mode, source
        # revision/digest and destination must all agree. No content leaks.
        return _stop("hook_context_snapshot_mismatch")
    return HookContextReview(())
