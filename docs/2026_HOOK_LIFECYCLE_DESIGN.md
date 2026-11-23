# Flame 2026.2.3 — single-Bootstrap lifecycle design (NO APPLY)

**Status: design only.** This document does not authorize a Flame Hook
installation. It deliberately adds no command to create, replace, remove,
reload, or modify files in Flame's Hook directories. The first executable
component remains the read-only, fail-closed
[`assess_bootstrap()`](2026_HOOK_PREFLIGHT.md) in Draft PR #6.

The scope is the sole Public `dgpy_bootstrap.py` entry point. Public Core
package source, optional Internal extensions, per-user settings, and any
machine-local Shared runtime are **not** recursively placed in a Hook
search directory.

Official source contracts:
- [Flame 2026 Python Hooks Reference](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Flame_API_Python_Hooks_Reference_html.html):
  User / Project / Application / Shared and `DL_PYTHON_HOOK_PATH` scopes,
  warning about duplicate Python filenames and different multiple-Hook
  behavior.
- [Flame 2026 Centralised Components](https://help.autodesk.com/cloudhelp/2026/ENU/FLAME-install-software-config/files/centralised_components.html):
  effective `sysconfig.cfg`, including redirected Shared `python` folder.

## 1. Separation of responsibilities

| Asset | Lifecycle owner | Proposal |
| --- | --- | --- |
| Public Bootstrap | Single selected Hook scope | Exactly one managed symlink, never a repository tree |
| Public Core package | Git checkout/package manager | Immutable reviewed revision, import path validated **inside isolated Flame** |
| Internal extension package | Internal-only checkout/config | Depends on Public in one direction; never leak internal files into Public |
| User runtime, configuration and update state | Flame/OS user-specific area | Separate backups, provenance and ownership |
| Machine-local Shared runtime | Per-machine deployment | Resolve symlinks/mounts and independently verify local execution body |
| Existing Autodesk or third-party Hooks | Their existing owners | Never overwrite, relocate, disable, or chmod |
| Flame user profile, Flame Setup Export/Import | Autodesk/application workflow | Not used as a DGpy installer or assumed to preserve DGpy files |

A User **or** a Shared Hook placement may be selected explicitly.
Never place the same Bootstrap in both scopes. Shared affects more users
and projects and therefore requires a distinct, more stringent
authorization. A macOS User path is not automatically a distinct Flame
User profile root; check Flame's effective environment independently.

## 2. Gated states and allowed intentions

The following are **future workflow states**, not implemented APIs:

| State | Meaning | Next action |
| --- | --- | --- |
| `OBSERVED` | Read-only root and source inventory gathered | No writes |
| `BLOCKED` | Unknown/conflicting/unsafe evidence | Stop; request manual remediation review |
| `PREVIEW_ONLY` | Limited static scan has no blocker | **Still no install permission** |
| `AUTHORIZED_ISOLATED` | Disposable OS/Flame profile and project, proven separate search roots, approved change window | Prepare an isolated-only plan |
| `PENDING_INSTALL` | Signed/recorded intent, exclusive destination vacancy rechecked | Later, separately reviewed installer only |
| `ACTIVE` | Unique managed link created and verified; separate Flame runtime tests pass | Observe and retain restore metadata |
| `DISABLED` | Only that managed link safely removed after matching the recorded identity | Code/config retained; startup/reload handled separately |
| `RECONCILE_MANUALLY` | Incomplete record, symlink changed, root changed, concurrent change or unowned file | No automatic removal or re-enable |

`PREVIEW_ONLY` -> `ACTIVE` is **not** a legal transition. Implementation
of state-changing operations requires separate design review and G3
isolated validation. This PR contains **no state-changing transition**.

## 3. Proposed prerequisites for any future installation

1. Freeze and record Public/Internal repository branch, commit, working-tree
   state, verified source revision/hash, and expected Flame 2026.2.3 runtime.
   Refuse an unreviewed or dirty checkout.
2. Derive **effective** User, current Project, Application, Shared and
   additional Hook search roots from the actual session (not guesses or
   only the shell). Inspect every known root, its ancestor symlinks,
   realpath/inode, name collisions and source aliases. Missing evidence
   is BLOCKED; a non-existent Project root is not equivalent to an
   unknown Project root.
3. Review ownership, permissions, ACLs, mount/network/locality, symlink
   target, root trust, and the **chosen target**. World-writable (e.g.
   `0777`) known roots are STOP conditions; **do not auto-chmod** to
   bypass them. Likewise do not auto-create any missing Hook root.
4. Confirm a **single** Bootstrap destination is absent with an
   exclusive/no-replace strategy. Do not rename, backup, overwrite or
   delete an existing destination on behalf of its owner.
5. Verify package import/runtime path, configuration separation, Menu
   contexts, restart/reload requirements and disable/recovery behavior in
   the disposable 2026.2.3 Flame environment **before** authorization
   for production is even considered.

The current `assess_bootstrap()` performs only a subset of step 2.
Its operator `Evidence=True` flags are attestations, not machine-verified
proof. The filesystem snapshot is **not atomic** and must never be treated
as permission for a later write without rechecking.

## 4. Proposed private transaction record

If a separate installer is approved in the future, it should maintain a
**private, outside-Hook** journal/manifest with restrictive permissions
and atomic per-file writes, including:

- transaction identifier; operation, state, timestamp and Flame version;
- exact selected scope, logical and resolved destination, source/revision
  and hash; baseline non-existence evidence;
- parent root identity (device/inode/owner), symlink target and **created
  symlink** identity captured after a successful exclusive create;
- all effective root inventory provenance, ACL/mount review identifier,
  consent/approval and any exception or interrupted step;
- no credentials, Project media, shot names, or production payloads.

Before creating a link, durably record **intent**; after exclusive create,
verify exact inode and link target and then record **committed**.
An interrupted transaction must go to `RECONCILE_MANUALLY` unless
ownership can be proven. Do not substitute Flame Setup's Profile ZIP for
the DGpy transaction record or claim that an exported Profile contains
DGpy Hook files without comparing its actual contents.

For a separate **future disable** operation, only an exact managed
`dgpy_bootstrap.py` symlink recorded by this transaction would be
eligible for unlink, and only after a fresh no-race verification of its
parent identity, link identity and target. A different file, a broken or
modified link, a missing journal, unexpected directory permissions, or
any change from the recorded state means **STOP and manual review**.
Never remove the whole Hook directory or alter unrelated Hooks.

**Re-enable** would require the same full preflight and explicit
authorization; disable does not imply a safe automatic restore.
**Revert** for a new placement means returning to the recorded
`destination absent` baseline, leaving source and user settings alone.
An existing Hook is never silently moved out to make space.
Handling an interrupted operation is a human-led reconciliation, not
a speculative `rm`, reset, or forced checkout.

## 5. Known gaps, testing and authorization

- No atomic multi-root snapshot, deep/masked Hook inventory, dynamic
  import detection, actual duplicate menu resolution, OS ACL evaluator,
  physical storage proof, safe transaction journal, or installer yet.
- Recheck root identity immediately before and immediately after any
  hypothetical operation; TOCTOU can still occur even with checks.
  Cross-machine Shared updates cannot be treated as one atomic operation.
- Run pure-Python planner/journal tests against disposable fixture trees
  first. Then verify Hook loading, only-once registration, all seven UI
  contexts, restart, user/project switching, error handling, and recovery
  in a **separately verified disposable** Flame 2026.2.3 installation.
- Maintain the internal G3/G4 NO-GO gates. Existing 2025.2.7
  `dgpy_dev.py setup --apply` and `dgpy-machine.sh` are not Flame
  2026 installers and must not be invoked for this validation.
- Production Hook writes, `chmod`/`chown`, symlink manipulation and
  Profile Reset/Import remain **NO-GO** until user-approved isolated
  validation and release criteria.

This is a **design proposal**, not a tested description of how Flame
manages third-party Hook installation or profile restoration.
