"""Read-only evidence review for a *previously recorded* DGpy Hook link.

This is NOT an installer, disabler, restorer, or authorization to unlink.
It returns only sanitized findings.  In particular, PREVIEW_ONLY means the
caller-supplied journal metadata matched a limited filesystem snapshot, not
that the journal is genuine, the snapshot is atomic, or a mutation is safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import stat

from .preflight import BOOTSTRAP_NAME, Finding, INSTALL_TARGET_SCOPES, VALIDATED_FLAME_VERSION


MAX_BOOTSTRAP_BYTES = 1024 * 1024


@dataclass(frozen=True)
class FileIdentity:
    """Private expected lstat identity, kept out of user-facing findings."""

    device: int
    inode: int
    owner_uid: int


@dataclass(frozen=True)
class ManagedLinkRecord:
    """Private input captured by a *separately verified* transaction journal.

    This record is untrusted until independently authenticated.  No journal
    parser, storage mechanism or state-changing transaction exists here.
    """

    flame_version: str
    scope: str
    state: str
    transaction_id: str
    hook_root: Path
    destination: Path
    source: Path
    raw_link_target: str
    root_identity: FileIdentity
    link_identity: FileIdentity
    source_identity: FileIdentity
    source_sha256: str


@dataclass(frozen=True)
class DisableReviewEvidence:
    """Operator attestations; True must be supported by separate evidence."""

    journal_authenticated: bool = False
    effective_roots_reviewed: bool = False
    security_reviewed: bool = False
    isolated_environment_confirmed: bool = False


@dataclass(frozen=True)
class DisableReview:
    """Non-actionable result that never contains paths or source names."""

    findings: tuple[Finding, ...]

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"


def _absolute_clean(value: object) -> bool:
    return isinstance(value, Path) and value.is_absolute() and ".." not in value.parts


def _has_symlink_ancestor(path: Path) -> bool:
    """Inspect from root outward, so an alias cannot silently redirect us."""
    for component in (*reversed(path.parents), path):
        if stat.S_ISLNK(component.lstat().st_mode):
            return True
    return False


def _valid_identity(value: object) -> bool:
    if not isinstance(value, FileIdentity):
        return False
    return all(
        isinstance(number, int) and not isinstance(number, bool) and number >= 0
        for number in (value.device, value.inode, value.owner_uid)
    )


def _matches(stat_result: os.stat_result, recorded: FileIdentity) -> bool:
    return (
        (stat_result.st_dev, stat_result.st_ino, stat_result.st_uid)
        == (recorded.device, recorded.inode, recorded.owner_uid)
    )


def assess_disable_preview(
    *,
    record: ManagedLinkRecord | None,
    evidence: DisableReviewEvidence = DisableReviewEvidence(),
) -> DisableReview:
    """Review a managed symlink without unlinking, writing or changing state.

    This does not verify journal authenticity, actual Flame Hook loading,
    user/profile separation, ACLs, physical mount locality or TOCTOU safety.
    There is intentionally no apply/disable/restore entry point.
    """
    findings: list[Finding] = []

    def stop(code: str, scope: str | None = None) -> None:
        findings.append(Finding(code, scope))

    if not isinstance(evidence, DisableReviewEvidence):
        stop("invalid_review_evidence")
        return DisableReview(tuple(findings))

    if evidence.journal_authenticated is not True:
        stop("journal_not_authenticated")
    if evidence.effective_roots_reviewed is not True:
        stop("effective_roots_unreviewed")
    if evidence.security_reviewed is not True:
        stop("ownership_acl_mount_unreviewed")
    if evidence.isolated_environment_confirmed is not True:
        stop("isolated_environment_unconfirmed")
    if findings:
        # No filesystem access until the full independent review is attested.
        return DisableReview(tuple(findings))

    if not isinstance(record, ManagedLinkRecord):
        stop("missing_or_invalid_managed_record")
        return DisableReview(tuple(findings))

    scope = (
        record.scope
        if isinstance(record.scope, str) and record.scope in INSTALL_TARGET_SCOPES
        else None
    )
    if scope is None:
        stop("unsupported_record_scope")
    if record.flame_version != VALIDATED_FLAME_VERSION:
        stop("unvalidated_record_version", scope)
    if record.state != "ACTIVE":
        stop("record_not_active", scope)
    if not isinstance(record.transaction_id, str) or not record.transaction_id.strip():
        stop("missing_transaction_id", scope)
    if findings:
        return DisableReview(tuple(findings))
    if (
        not _valid_identity(record.root_identity)
        or not _valid_identity(record.link_identity)
        or not _valid_identity(record.source_identity)
    ):
        stop("invalid_recorded_identity", scope)
        return DisableReview(tuple(findings))

    if (
        not _absolute_clean(record.hook_root)
        or not _absolute_clean(record.destination)
        or not _absolute_clean(record.source)
        or record.destination.parent != record.hook_root
        or record.destination.name != BOOTSTRAP_NAME
        or record.source.name != BOOTSTRAP_NAME
        or record.hook_root == record.source
        or record.hook_root in record.source.parents
    ):
        stop("invalid_record_paths", scope)
        return DisableReview(tuple(findings))
    if (
        not isinstance(record.source_sha256, str)
        or len(record.source_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in record.source_sha256)
    ):
        stop("invalid_recorded_source_digest", scope)
        return DisableReview(tuple(findings))
    if (
        not isinstance(record.raw_link_target, str)
        or not record.raw_link_target
        or record.raw_link_target != str(record.source)
    ):
        stop("invalid_record_link_target", scope)
        return DisableReview(tuple(findings))

    try:
        if _has_symlink_ancestor(record.hook_root):
            stop("hook_root_alias_present", scope)
            return DisableReview(tuple(findings))
        root = record.hook_root.lstat()
        if not stat.S_ISDIR(root.st_mode):
            stop("hook_root_not_directory", scope)
            return DisableReview(tuple(findings))
        if not _matches(root, record.root_identity):
            stop("hook_root_identity_changed", scope)
        if root.st_mode & stat.S_IWOTH:
            stop("world_writable_hook_root", scope)
    except OSError:
        stop("hook_root_inspection_failed", scope)
        return DisableReview(tuple(findings))
    if findings:
        return DisableReview(tuple(findings))

    try:
        link = record.destination.lstat()
        if not stat.S_ISLNK(link.st_mode):
            stop("managed_link_not_symlink", scope)
            return DisableReview(tuple(findings))
        if not _matches(link, record.link_identity):
            stop("managed_link_identity_changed", scope)
        if os.readlink(record.destination) != record.raw_link_target:
            stop("managed_link_target_changed", scope)
    except OSError:
        stop("managed_link_inspection_failed", scope)
        return DisableReview(tuple(findings))
    if findings:
        return DisableReview(tuple(findings))

    # The link target may be replaced while the link inode stays constant.
    # This is still only a snapshot: the source revision/hash must be
    # independently authenticated in a separate protected journal.
    try:
        if _has_symlink_ancestor(record.source):
            stop("source_alias_present", scope)
            return DisableReview(tuple(findings))
        source_stat = record.source.lstat()
        if not stat.S_ISREG(source_stat.st_mode):
            stop("source_not_regular_file", scope)
            return DisableReview(tuple(findings))
        if not _matches(source_stat, record.source_identity):
            stop("source_identity_changed", scope)
        if source_stat.st_mode & stat.S_IWOTH:
            stop("source_world_writable", scope)
            return DisableReview(tuple(findings))
        if source_stat.st_size > MAX_BOOTSTRAP_BYTES:
            stop("source_unexpectedly_large", scope)
            return DisableReview(tuple(findings))
        # Open the recorded source read-only without following a final symlink.
        # O_NONBLOCK prevents an unexpected FIFO replacement from hanging.
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            stop("source_nofollow_unavailable", scope)
            return DisableReview(tuple(findings))
        fd = os.open(record.source, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or not _matches(opened, record.source_identity):
                stop("source_changed_during_review", scope)
                return DisableReview(tuple(findings))
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        if digest.hexdigest() != record.source_sha256:
            stop("source_digest_changed", scope)
        if not _matches(record.source.lstat(), record.source_identity):
            stop("source_changed_during_review", scope)
    except OSError:
        stop("source_inspection_failed", scope)

    # Recheck both inode identities to detect a subset of concurrent changes.
    # Even two matching reads are NOT atomic and do NOT authorize unlink.
    try:
        if not _matches(record.hook_root.lstat(), record.root_identity):
            stop("hook_root_changed_during_review", scope)
        final_link = record.destination.lstat()
        if (
            not stat.S_ISLNK(final_link.st_mode)
            or not _matches(final_link, record.link_identity)
            or os.readlink(record.destination) != record.raw_link_target
        ):
            stop("managed_link_changed_during_review", scope)
    except OSError:
        stop("review_race_or_stat_failure", scope)
    return DisableReview(tuple(findings))
