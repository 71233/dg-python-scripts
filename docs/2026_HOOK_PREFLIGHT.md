# Flame 2026.2.3 Hook deployment preflight (experimental)

## Read-only generation-bound HMAC v2 (no automatic fallback)

The experimental [v2 anchor review](2026_HOOK_ANCHOR_V2_PREVIEW.md)
adds an independent in-memory validator that MAC-binds
`key_generation` plus the transaction identity, scope, revision,
terminal state and journal SHA-256 tip. The previous v1 custody
review remains unchanged and blocks generation 2+; this is **not**
a production key rotation or migration.

Disposable Python 3.13.5 tests: **63/63** v2 fixtures, or **186/186**
combined with available existing preflight, journal and lifecycle
fixtures. The code and tests parse under Python 3.11 grammar.
**Current PR-head full Public Python 3.11 CI remains a separate gate**.
Flame's exact macOS Python 3.11.5 and actual Hook operation remain
unverified. All preview results are non-actionable.

## Custody-aware recovery preview (pure Python, NO APPLY)

[Read-only key custody/recovery gating](2026_KEY_CUSTODY_RECOVERY_PREVIEW.md)
is added as a companion to the HMAC anchor verifier. It checks the
purported external revocation/retirement status and independently
attested latest revision **before** invoking HMAC verification;
generation 2+ is unsupported under anchor v1 and always BLOCKS.
Interrupted or inconsistent histories require manual reconciliation
without any file changes. Matching records only produce `NO_CHANGE`.

The new tests comprise **44 mocked custody boundary checks** and
**9 actual HMAC/journal integration fixtures**. The mocked cases passed
locally on Python 3.13.5; [GitHub Actions CI 45168207871](https://github.com/71233/dg-python-scripts/actions/runs/45168207871)
passed the **267-case full Public suite** and wheel build on Ubuntu 24.04
/ Python 3.11. The exact macOS Flame 2026.2.3 Python 3.11.5 runtime
remains unverified.

## Latest isolated HMAC anchor review (NO APPLY)

The new [HMAC anchor preview](2026_HOOK_HMAC_ANCHOR_REVIEW.md)
adds `JournalAnchor`, `AnchorReviewEvidence`, and
`assess_hmac_journal_preview()` as another **pure in-memory** assessment.
This does not sign/store keys or journals, authenticate external key
provenance, touch Flame, or perform a state-changing action. HMAC binds
expected identity/revision and an externally supplied key to a journal
tip, then delegates to the existing chain review. Missing or
untrustworthy external evidence returns `BLOCKED`; even a matching
HMAC is **not authorization to unlink/install/restore**.

The isolated Python 3.13.5 deployment subset now passes **168/168**
tests (existing 38 preflight + 42 managed-link + 43 journal + **45 HMAC**
fixtures). Python 3.11 grammar parsing succeeded for the new modules
and tests. The new [GitHub Actions CI run 45163143326](https://github.com/71233/dg-python-scripts/actions/runs/45163143326)
**passed** on Ubuntu 24.04 / Python 3.11: editable package install,
**214/214 unittest cases** (including the 45 new HMAC fixtures), and
a successful wheel build. This does **not** verify the exact macOS
Flame 2026.2.3 Python 3.11.5 or real Hook/UI/Selection behaviour.

This is a **read-only, fail-closed assessment** for planning DGpy's single
`dgpy_bootstrap.py` placement. It is **not an installer**, repair utility,
or authorization to touch production Flame Hook directories. The implementation does not include a CLI or an `apply` action; neither
preflight nor the companion disable preview can modify Hook files.

The shared module lives in `src/dg_python_scripts/deployment/preflight.py`.
It imports no Flame, Qt, or PySide modules. The public DGpy bootstrap remains
the sole proposed DGpy entry point in Flame's Hook search paths. The 2025.2.7
setup scripts in Public draft PR #4 are **not** used or modified by this work.

## Documented search scopes and limitations

The Autodesk Flame 2026 Hook Reference documents User, Project, Application,
Shared, and optional `DL_PYTHON_HOOK_PATH` directories:

- https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Flame_API_Python_Hooks_Reference_html.html
- https://help.autodesk.com/cloudhelp/2026/ENU/FLAME-install-software-config/files/centralised_components.html

`assess_bootstrap()` takes an **explicit list** of `HookRoot` objects. It
does not guess the active Project, infer User HOME, parse sysconfig on its
own, or automatically enumerate the effective Hook roots. This prevents a
successful-looking result caused by an incomplete directory search.

An operator must provide exactly one root for each standard scope (User,
Project, Application, Shared) and a separate `scope="extra"` entry for each
confirmed additional Hook directory. `path=None` means unknown, not absent.
A known directory that does not exist is distinct from an unknown root.
A **non-target** User directory (possibly not created before first launch)
or Project directory may be absent. A missing target **User or Shared**,
Application, non-target Shared, or explicitly supplied extra directory
BLOCKS the assessment. The function never creates any directory.

The `Evidence` flags are explicit **operator attestations**. By default all
are unknown and the assessment is BLOCKED. They include a confirmed exact
Flame version (`2026.2.3` for this initial prototype), complete known standard
roots, the verified completeness of additional path entries, independent
ownership/ACL/mount review, and source checkout/revision provenance. Setting
any flag to True without real evidence invalidates the assessment.

## Static checks

- Reject missing/duplicate standard scopes, unknown extra search roots,
  relative paths, path traversal, wrong target scope, or wrong Flame version.
- Reject source missing, wrong filename, non-regular source, a symlink in the
  source or its ancestors, world-writable source, or source within a Hook root.
- Reject a missing target or unexpected missing non-target Hook directory,
  non-directory roots, a symlink in any supplied root path, unreadable roots,
  duplicate root paths/inodes, **or overlapping ancestor/descendant roots**.
- Reject **any world-writable inspected Hook root**, including one not used
  as the target. The observed 0777 User/Shared roots in the 2026.2.3
  environment will therefore BLOCK the plan; no `chmod` workaround is made.
- Reject any `dgpy*`/`dg_python_scripts*` direct entry, including dangling
  symlinks; existing files are **never overwritten**, even if a symlink might
  point to the same source.
- Reject direct `.py` symlinks, duplicate case-folded `.py` basenames among
  supplied roots, **direct hard links to the selected Bootstrap source**,
  and entry/root changes that make an in-progress scan inconsistent.
  Filename folding is conservative on potentially case-insensitive macOS
  filesystems; it does not claim Flame's loader is case-insensitive.

Findings contain only stable issue codes and standard scope identifiers, **no
hostnames, Project names, actual filenames, file contents, or private paths**.
`report.status` is either `BLOCKED` or `PREVIEW_ONLY`.
**`PREVIEW_ONLY` does not mean safe to install**: it merely means this limited
static scanner did not find a blocker with the supplied and attested inputs.

## Deliberate exclusions

This version does **not** verify real Hook loading, arbitrary alternate
filenames or dynamic imports, recursive subdirectories, content-identical
copies with different inodes, hidden hard-link aliases outside supplied
direct `.py` entries, actual Flame import paths, per-Project behavior
beyond one explicitly supplied
Project root, all system users, menu/UI registration, or the root priority
order. It does not determine whether a machine's storage is physically local,
or validate ACLs, network mounts, user ownership, and symlink races in depth.
The corresponding `Evidence.security_reviewed=True` remains an **external
review**, not a platform security guarantee. The check is not atomic;
filesystem contents may change before any eventual installation.

Directory scans are non-mutating but can trigger filesystem access-time
changes or remote automount activity. They must be run only on authorized
paths and stopped if a shared mount is unresponsive.

## Testing and project gates

Run in a disposable checkout/fixture environment, not by installing in Flame:

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_deployment_preflight.py' -v
```

The initial 29 disposable-directory tests were extended with nine regression
tests covering non-target missing directories, overlapping Hook roots,
hard-linked Bootstrap aliases, disappearing directories and failed entry
stat checks. All **38 isolated fixture tests** passed on Python 3.13.5,
and the changed code and tests parsed under Python 3.11 grammar.

GitHub Actions
[CI run 45156440211](https://github.com/71233/dg-python-scripts/actions/runs/45156440211)
**passed** on Ubuntu 24.04 / Python 3.11 with an editable install,
**84/84 unittest cases** (38 preflight fixtures including nine new regression
tests, plus the existing Public tests) and a successful wheel build.
This verifies the reviewed code on Linux Python 3.11, **not** the exact
Flame-shipped Python 3.11.5 on macOS or real Flame Hook/menu behavior.
Do not present these unit tests as Flame 2026 integration testing.

See also [single-Bootstrap installation, disable and recovery design
(NO APPLY)](2026_HOOK_LIFECYCLE_DESIGN.md). The companion read-only
`assess_disable_preview()` in `deployment/lifecycle.py` reviews an
independently authenticated, previously recorded managed Bootstrap symlink
**only inside a separately verified disposable environment**. It compares
the Hook root, link, source identities and source SHA-256 with a supplied
record; its findings are sanitized. There is **no journal reader/writer and
no code that installs, disables, restores or changes a Hook**.

The new `tests/test_deployment_lifecycle.py` adds **42 disposable-fixture
tests** for absent/inauthentic evidence, unexpected metadata, world-writable
roots, links replaced by files, missing sources, source edits, symlink
aliases, SHA-256 mismatches, I/O failures and non-mutation. Together with
the existing 38 preflight tests, **80/80 isolated Python 3.13.5 tests**
passed in a disposable workspace; the new files parsed as Python 3.11
grammar. GitHub Actions
[CI run 45159372263](https://github.com/71233/dg-python-scripts/actions/runs/45159372263)
**passed** on Ubuntu 24.04 / Python 3.11: editable package installation,
**126/126 unittest cases** (42 new lifecycle, 38 existing preflight, and
46 other Public tests), and a successful wheel build.
This CI does **not** validate the exact macOS Flame 2026.2.3 bundled
Python 3.11.5, real Hook loading, UI/Selection, or Profile restoration.
A production Mac is **not** used as a test fixture.

### Proposed in-memory journal consistency preview

A separate pure-Python [journal review](2026_HOOK_JOURNAL_REVIEW.md)
validates an at-most-five-event proposed v1 sequence, deterministic
SHA-256 chain, and a separately supplied expected tip. It requires explicit
external attestation of independent tip verification and **isolated**
environment; missing evidence BLOCKS without touching events. It has no
journal disk I/O, install/disable/restore actions, or private data output.
A complete chain is only `PREVIEW_ONLY`; incomplete transactions, missing
steps and hash mismatches all BLOCK. **SHA-256 is not a signature**: a chain
is not authenticated if an attacker can replace its trusted tip too.

The added `tests/test_deployment_journal.py` contains **43 in-memory
regression tests**, including four hostile subclass input cases;
together with 38 preflight and 42 disable-preview tests,
the isolated Python 3.13.5 subset passed **123/123**. The new code parsed
with Python 3.11 grammar. The new [GitHub Actions CI run 45161220740](https://github.com/71233/dg-python-scripts/actions/runs/45161220740)
**passed** on Ubuntu 24.04 / Python 3.11 with editable install,
**169/169 unittest cases** (43 journal + 42 lifecycle + 38 preflight +
46 other Public tests), and a successful wheel build. This is **not**
Flame 2026.2.3's exact Python 3.11.5 on macOS or a runtime Hook test.

Next stages, each requiring separate evidence:

1. Review correctness and compatibility with the Public existing tests/CI,
   including actual Python 3.11.5 execution, and collect review feedback.
2. Add only a separately reviewed preview of source/target and rollback
   actions. Do **not** add an `apply` path until safe failure/rollback and
   ownership/mount proof are accepted.
3. Validate one isolated/disposable Flame 2026.2.3 User/Project and a single
   Bootstrap, its UI appearance, restart/reload behavior, context selection,
   duplicate avoidance, and restoration.
4. Only after isolated success and explicit authorization, consider
   production deployment. Production Hook writes and Profile Reset/Import
   remain **NO-GO** in this development stage.
