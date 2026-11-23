# Flame 2026.2.3 — effective Hook context and deployment ID preview (NO APPLY)

**Status: experimental, isolated-test-only and non-operational.**
`assess_hook_context_preview()` in
`src/dg_python_scripts/deployment/hook_context_review.py` compares
**two separately supplied in-memory records**: a proposed authenticated
deployment binding and an independently observed effective Hook context.
It does not load `flame` or Qt, call `lstat`, read `sysconfig.cfg`,
resolve symlinks, access Git, write a journal, install, enable, disable,
restore or remove any Hook. **No automatic system discovery or authority
is implemented.**

Official 2026 source contracts:

- [Autodesk Flame Python Hooks Reference](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Flame_API_Python_Hooks_Reference_html.html):
  User, Project, Application, Shared and additional
  `DL_PYTHON_HOOK_PATH` roots, with duplicate Hook file naming caveats.
- [Autodesk Flame Centralised Components](https://help.autodesk.com/cloudhelp/2026/ENU/FLAME-install-software-config/files/centralised_components.html):
  an effective `sysconfig.cfg` can redirect Shared `python`; a network
  directory being unavailable may cause a **fallback to factory paths**.
  A static path list alone does not prove which root was actually loaded.

## What the preview checks

The immutable `HookContextRecord` holds a generic `deployment_id`,
Flame version, selected User or Shared target, destination, bootstrap
source location, externally reviewed full source revision (40 or 64
lowercase hexadecimal), source SHA-256 and an **ordered** tuple of
`RootSnapshot` entries. Each root has a scope, POSIX absolute path,
presence, and when present, device/inode/owner-UID/mode metadata.
There must be exactly one of each standard root; additional roots
are individually labelled `extra` (24-root bound for this first
prototype). **Root order is compared**; it is not inferred to match
Flame loader precedence.

The function checks that:

- An independent expected deployment ID and target scope match **both**
  records. Deployment ID and target scope are not inferred from filenames
  or local usernames.
- Both records specify Flame `2026.2.3`, structurally valid paths and
  source hashes/revisions, and the exact expected
  `dgpy_bootstrap.py` destination under the selected root.
- The four standard scope entries are complete. Only a **non-target**
  User or Project root is permitted to be *known but absent*.
  Application, Shared, extra or the selected root being absent BLOCKS.
- Roots do not duplicate or overlap lexically; present root
  device/inode pairs do not duplicate; dangerous world-writable modes
  such as `0777` BLOCK. A source inside the Hook root also BLOCKS.
- The complete **ordered** observed root collection, path and
  device/inode/owner/mode metadata, destination, source revision,
  source digest and deployment ID exactly match the separately
  supplied binding. Any difference BLOCKS.

`HookContextEvidence` requires independent confirmation of the
binding's origin, **actual effective** roots, additional paths,
resolved `sysconfig.cfg`, Shared failover state, current Project
context, root metadata/symlink/ACL/mount observations, source revision
and an **isolated disposable test environment**. An unconfirmed field
returns `BLOCKED` before either record is inspected.

**Crucial limitation:** These `True` attestations and two matching
records do **not** authenticate the binding issuer, prove a live Flame
session's loader paths, establish a root's physical storage identity,
or detect a symlink from an input path. `stat` fields are **supplied
metadata**, not measurements made by this function. A malicious
source controlling both records and attestations can fabricate a
`PREVIEW_ONLY` result. A fixture test documents that behavior.

## Privacy, output and future architecture

The private `HookContextRecord` input may include real paths and
source information in a later **separately approved** isolated
environment; the result contains **only generic finding codes**.
No hostnames, usernames, raw paths, Project/shot names, source hash,
deployment ID or file payload appear in returned findings.
Production paths, hostnames, keys and journals must not enter
the Public repository, CI fixtures or chat.

`PREVIEW_ONLY / NO_CHANGE` means **only** two in-memory records
agreed under the supplied attestations. `BLOCKED /
MANUAL_RECONCILIATION` requires review, **not** an instruction to
delete, reload, retry, chmod or reset Flame. There is no state-changing
method on `HookContextReview`.

The v2 [HMAC deployment ID preview](2026_HOOK_ANCHOR_V2_PREVIEW.md)
authenticates the **claimed** deployment ID, but does **not**
cryptographically bind the full effective root inventory.
This new context comparison is **not automatically chained** to v2
and cannot be used to set its trust flags without independently
authenticated evidence. Issuer/identity lifecycle, an authenticated
current-root capture, monotonic checkpoint, atomic state transitions
and an unambiguous binding to the actual installed source are all
future G3/G4 gates, not claimed features.

## Verification and remaining NO-GO

The **39 disposable/in-memory** unit cases in
`tests/test_deployment_hook_context.py` passed on **Python 3.13.5**
without calling any filesystem APIs. They cover User/Shared/extra
roots, missing optional/required roots, root identity and order,
world-writable roots, nested/duplicate scopes and inode aliases,
changed source SHA/revision, malformed paths, missing external
attestations, safe findings and fabricated self-consistent inputs.
The new source parses on Python 3.11 grammar; the exact code/test
blob SHAs match the isolated test artifacts.

[GitHub Actions CI run 45186664368](https://github.com/71233/dg-python-scripts/actions/runs/45186664368)
**passed** on Ubuntu 24.04 / Python **3.11**: **379/379 Public
unittest cases** (including all 39 new Hook context tests), editable
package installation and wheel build. This is **not** the exact
Flame-bundled Python 3.11.5 on macOS or a live Hook loader test.
The only available Flame 2026.2.3 Mac is used for production;
no approved isolated Flame host is available.

**NO-GO:** Production Hook write/rename/delete, symlink creation,
chmod/chown, restart/reload, Flame Setup Profile Reset/Import,
installing a Bootstrap to force a test, and merging the Draft PRs.
See [2026 Hook preflight](2026_HOOK_PREFLIGHT.md) and
[NO-APPLY lifecycle](2026_HOOK_LIFECYCLE_DESIGN.md).
