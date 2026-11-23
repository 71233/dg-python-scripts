"""Read-only, fail-closed Flame 2026.2.3 Hook placement assessment.

This module never creates, fixes, replaces, imports, or loads a Flame Hook.
It is a limited static preflight, NOT authorization for a production install.
The caller must independently establish the effective Hook search roots and
review ownership, ACLs and storage. A missing fact is a blocking finding.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Iterable


BOOTSTRAP_NAME = "dgpy_bootstrap.py"
VALIDATED_FLAME_VERSION = "2026.2.3"
STANDARD_SCOPES = frozenset({"user", "project", "application", "shared"})
INSTALL_TARGET_SCOPES = frozenset({"user", "shared"})
# A non-target User or Project Hook root may legitimately not exist yet.
_OPTIONAL_MISSING_SCOPES = frozenset({"user", "project"})
_DGPY_PREFIXES = ("dgpy", "dg_python_scripts")


@dataclass(frozen=True)
class HookRoot:
    """One explicitly identified Hook root; path=None means unconfirmed.

    scope is one of the four standard scopes or 'extra' for each additional
    DL_PYTHON_HOOK_PATH entry. Extra roots may repeat and are not named in
    assessment output to avoid exposing private path labels.
    """

    scope: str
    path: Path | None


@dataclass(frozen=True)
class Evidence:
    """Operator attestations: never inferred automatically from directories.

    All fields default to unknown. A True flag is not proof: operators must
    base it on independent inspection of Flame's effective configuration.
    """

    flame_version: str | None = None
    roots_confirmed: bool = False
    additional_paths_confirmed: bool = False
    security_reviewed: bool = False
    source_provenance_reviewed: bool = False


@dataclass(frozen=True)
class Finding:
    """No raw paths or filenames from the workstation leave this report."""

    code: str
    scope: str | None = None


@dataclass(frozen=True)
class PreflightReport:
    findings: tuple[Finding, ...]
    inspected_roots: int

    @property
    def status(self) -> str:
        # PREVIEW_ONLY deliberately does not mean that installation is safe.
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"


def _validated_path(value: Path | None) -> Path | None:
    if value is None or not isinstance(value, Path):
        return None
    if not value.is_absolute() or ".." in value.parts:
        return None
    return value


def _has_symlink_component(path: Path) -> bool:
    for component in (*reversed(path.parents), path):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            return True
    return False


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def assess_bootstrap(
    *,
    source: Path,
    roots: Iterable[HookRoot],
    target_scope: str,
    evidence: Evidence = Evidence(),
) -> PreflightReport:
    """Inspect known direct Hook entries without mutating any filesystem state.

    Returns BLOCKED unless a complete caller-supplied root contract and a
    conservative, collision-free filesystem snapshot are present. Even a
    PREVIEW_ONLY result is not approval to install: this checks neither
    runtime Hook loading nor nested/dynamic imports, ACLs, network locality,
    filesystem races, or rollback. There is intentionally NO apply method.
    """
    findings: list[Finding] = []
    items = tuple(roots)

    def stop(code: str, scope: str | None = None) -> None:
        findings.append(Finding(code, scope))

    if evidence.flame_version != VALIDATED_FLAME_VERSION:
        stop("unvalidated_flame_version")
    if not evidence.roots_confirmed:
        stop("effective_roots_unconfirmed")
    if not evidence.additional_paths_confirmed:
        stop("additional_paths_unconfirmed")
    if not evidence.security_reviewed:
        stop("ownership_acl_mount_unreviewed")
    if not evidence.source_provenance_reviewed:
        stop("source_revision_unreviewed")
    if target_scope not in INSTALL_TARGET_SCOPES:
        stop("unsupported_target_scope")

    standard_seen: set[str] = set()
    known_paths: list[tuple[str, Path]] = []
    for item in items:
        scope = item.scope if item.scope in STANDARD_SCOPES else "extra"
        if item.scope not in STANDARD_SCOPES and item.scope != "extra":
            stop("invalid_scope", scope)
            continue
        if item.scope in STANDARD_SCOPES:
            if item.scope in standard_seen:
                stop("duplicate_scope", item.scope)
            standard_seen.add(item.scope)
        path = _validated_path(item.path)
        if path is None:
            stop("unknown_or_invalid_root", scope)
            continue
        known_paths.append((scope, path))

    for scope in sorted(STANDARD_SCOPES - standard_seen):
        stop("missing_scope", scope)

    # Overlapping search roots can cause the same code to be visited twice,
    # even when no direct basename collision is present today.
    for index, (scope, path) in enumerate(known_paths):
        for _, previous in known_paths[:index]:
            if path != previous and (_within(path, previous) or _within(previous, path)):
                stop("overlapping_hook_roots", scope)

    clean_source = _validated_path(source)
    source_identity: tuple[int, int] | None = None
    if clean_source is None:
        stop("invalid_source_path")
    else:
        if clean_source.name != BOOTSTRAP_NAME:
            stop("unexpected_source_name")
        try:
            if _has_symlink_component(clean_source):
                stop("source_path_contains_symlink")
            else:
                s = clean_source.lstat()
                if not stat.S_ISREG(s.st_mode):
                    stop("source_not_regular_file")
                else:
                    source_identity = (s.st_dev, s.st_ino)
                if s.st_mode & stat.S_IWOTH:
                    stop("source_world_writable")
                if not os.access(clean_source, os.R_OK):
                    stop("source_not_readable")
        except FileNotFoundError:
            stop("source_missing")
        except OSError:
            stop("source_stat_failed")
        for scope, path in known_paths:
            if _within(clean_source, path):
                stop("source_inside_hook_root", scope)

    inspected = 0
    inspected_identities: set[tuple[int, int]] = set()
    seen_paths: set[Path] = set()
    hook_names_seen: set[str] = set()
    for scope, path in known_paths:
        if path in seen_paths:
            stop("duplicate_root_path", scope)
        seen_paths.add(path)
        path_was_present = False
        try:
            if _has_symlink_component(path):
                stop("root_path_contains_symlink", scope)
                continue
            st = path.lstat()
            path_was_present = True
            if not stat.S_ISDIR(st.st_mode):
                stop("root_not_directory", scope)
                continue
            identity = (st.st_dev, st.st_ino)
            if identity in inspected_identities:
                stop("duplicate_root_identity", scope)
            inspected_identities.add(identity)
            if st.st_mode & stat.S_IWOTH:
                stop("world_writable_hook_root", scope)
            if scope == target_scope and not os.access(path, os.W_OK | os.X_OK):
                stop("target_not_accessible", scope)
            with os.scandir(path) as entries:
                names = [(entry.name, entry.is_symlink()) for entry in entries]
            inspected += 1
            if any(name.lower().startswith(_DGPY_PREFIXES) for name, _ in names):
                stop("dgpy_candidate_present", scope)
            if any(link and name.casefold().endswith(".py") for name, link in names):
                stop("hook_file_symlink_present", scope)
            for name, _ in names:
                if not name.casefold().endswith(".py"):
                    continue
                folded_name = name.casefold()
                if folded_name in hook_names_seen:
                    stop("duplicate_hook_basename", scope)
                hook_names_seen.add(folded_name)
                # A hard link may disguise the DGpy bootstrap under a
                # different filename. Compare identity, never file content.
                if source_identity is not None:
                    candidate = path / name
                    try:
                        candidate_stat = candidate.lstat()
                    except OSError:
                        stop("hook_entry_stat_failed", scope)
                    else:
                        if (candidate_stat.st_dev, candidate_stat.st_ino) == source_identity:
                            stop("bootstrap_hardlink_alias_present", scope)
        except FileNotFoundError:
            if path_was_present:
                stop("root_changed_during_scan", scope)
            elif scope == target_scope:
                stop("target_root_missing", scope)
            elif scope not in _OPTIONAL_MISSING_SCOPES:
                stop("unexpected_non_target_root_missing", scope)
        except OSError:
            stop("root_inspection_failed", scope)

    # Intentionally not checking modes of ancestors, ACLs, actual Hook loader
    # state, network mount identity, dynamic aliases, or concurrent changes.
    return PreflightReport(tuple(findings), inspected)
