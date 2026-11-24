# Flame 2026.2.3 — Rename / Delete Markers plan safety review (NO APPLY)

**Status: experimental, isolated G2, read-only and not connected to a live Hook.**
`actions/plan_safety_review.py` adds
`review_rename_plan()`, `review_marker_delete_plan()` and an
`ActionPlanReview` diagnostic. They inspect the **already captured**
pure-Python `RenamePlan` and `MarkerDeletePlan` dataclass structures
from existing Public DGpy, **not the current Flame host**.

Neither function reads `name.get_value()`, `markers`, a live Selection,
a current reel or an object's `selected` property; they never call
`set_value()`, `flame.delete()`, `apply_plan()`, `apply_delete_plan()`,
Qt, filesystem operations or any Hook. They are **not invoked by the current menus**. This Draft branch now
also includes **separate, narrowly scoped fixes to the existing**
`rename.py` and `markers.py` apply paths, verified only with synthetic
failure injection and Linux CI; it has not been merged or deployed.

## 2026-11-24 — failure-injection regression and narrow Draft-only fixes

Disposable Python reproductions of the **pre-fix algorithms** demonstrated:

- A temporary Rename setter changing a second target and then raising
  leaves the second target with a temporary name while the previous
  target is restored.
- A stale marker list on a later target permits deleting an earlier
  target's markers before the stale list is discovered.

The patched **Public Draft PR #7** changes only
`src/dg_python_scripts/rename.py` and
`src/dg_python_scripts/markers.py` plus synthetic tests/docs.
It does **not** modify the existing Hook, menu, SelectionBroker, Qt UI,
deletion dialog or bootstrap. The new marker error inherits from the
existing `MarkerApplyError`, so the existing UI catches it and
reports that zero markers were deleted when the preflight stops.

The new `tests/test_action_failure_injection_2026.py` has **13
regression cases**: partial setter failure, transient read-back failure,
failed restore reporting, pre-apply stale Rename, healthy rename,
added/removed/replaced/reordered markers, unreadable later target,
healthy deletion, and simulated dialog-confirmation-time state change.

[Public PR #7 GitHub Actions 45299428735](https://github.com/71233/dg-python-scripts/actions/runs/45299428735)
passed **145/145 Python 3.11 unit tests**, editable installation and
wheel build on Ubuntu 24.04. An initial CI attempt exposed a **test
fixture error**: an unreadable marker target used an unsupported class
name and was excluded by the existing target collector. After
changing the fixture to a supported `PySequence` and asserting two
targets were collected, the full CI passed. No Flame object was used
or modified.

**Not established:** actual Flame Python 3.11.5 behavior, pointer/proxy
stability, callback Selection equivalence, safe concurrent edits,
atomicity, per-project namespace rules or complete rollback.
These are **G3** requirements. The branch remains Draft and must
not be merged or deployed on the user's only production Mac.

## Supported evidence and limits

| Existing operation | Pure model can detect | What it **cannot** establish |
| --- | --- | --- |
| Rename `build_plan()` → `apply_plan()` | Missing/invalid rows; unsupported or contradictory status; duplicate Python object identity; repeated `name_attribute` wrapper identity; invalid, blank or control-character target names; multiple requested changes with the same proposed name; empty/no-change plans | Whether the actual Flame attribute is writable; object identity remains stable across callback phases; uniqueness of names in the real reel/folder; whether the current name is still the previewed name; partial-write and rollback safety |
| Delete Markers `build_delete_plan()` → `apply_delete_plan()` | Invalid target/marker snapshots; duplicate target identity; duplicate captured marker references even across targets; absence of captured markers; unsupported target type-name hints | Whether a `PyClip` / `PySequence` name denotes an actual Flame object, whether any marker is *still* on the target, whether the target is modifiable, or whether a deletion can be undone |

Both functions are deliberately conservative: 256-target upper bound,
exact immutable dataclass types and exact tuple fields, generic finding
codes, no host objects in returned reports. When several requested
names coincide, `unverified_rename_name_collision` **blocks even if
the names would be valid in distinct host namespaces**. The correct
resolution requires a real, independently validated namespace check,
**not** suppressing this block or guessing a directory from a class name.

`PREVIEW_ONLY / NO_CHANGE` means **only** that the captured snapshot
has no modeled structural contradiction. Every result retains
`requires_live_recheck=True`; Delete Markers also retains
`requires_operator_confirmation=True`. This is **not an action
authorization**. No automatic caller is connected to these results.

## Existing source review — behavior, risks, and verification gate

### Rename

The existing `rename.probe_target()` reads `name.get_value()` and
looks for `set_value()`. It cannot prove the setter succeeds.
`rename.apply_plan()` reads current names before starting and
uses temporary names and rollback steps to handle name swaps.
These are **existing implementation observations**, not tested
Flame 2026.2.3 behavior.

**Confirmed in a synthetic failure-injection reproducer:** the previous
temporary rename path recorded a row for rollback only *after*
`_write_exact()` returned. A setter that changed the value then raised
left the failed target at a temporary name. This Draft branch now
records every **attempted** temporary target before invoking the
setter, and attempts to restore all attempted targets in reverse
order. It skips a redundant restore when the target still has its
original name and records any restoration failure in
`RenameApplyError.rollback_errors`.

**Residual limitation:** This is a best-effort compensation procedure,
not a host transaction. If the original name cannot be read or restored
or the setter has undocumented side effects, recovery can still fail.
A passing Python test cannot establish Flame 2026.2.3 transactional
semantics or collision-free namespaces.

Before any future operation on a safe test host, a separately verified
adapter needs to establish fresh Selection identity at **execute**
time, target capabilities, live name read-back, namespace collisions
and a recovery/restore procedure. Do not inherit 2025.2.7
right-click/shortcut Selection assumptions without 2026.2.3 evidence.

### Delete Markers

Existing `markers.build_delete_plan()` reads `PyClip` /
`PySequence` marker collections (and direct `PyReel` children).
`delete_markers_action.show_delete_markers()` displays a destructive
confirmation dialog and calls `flame.delete(marker, confirm=False)`
only after confirmation.

**Confirmed in a synthetic failure-injection reproducer:** the
previous `markers.apply_delete_plan()` could delete markers from
the first target before discovering that a later target's
captured marker collection was stale. In this Draft branch, the
apply path now re-reads **every target's** marker collection before
the first delete callback. It conservatively requires matching
collection length **and matching Python proxy identity in order**.
A difference or an unreadable collection raises
`StaleMarkerDeleteError(MarkerApplyError)` with `deleted=0`, using
the **existing error-dialog handler**. It does not call the delete
callback on that preflight failure.

**Residual limitation:** A re-check is not atomic with deletion,
and Flame might materialize fresh Python proxy objects across reads.
A valid plan could be rejected, or the host could still change after
preflight. The structural plan reviewer remains independent and
does not eliminate this time-of-check/time-of-use gap.

Even a separate read-back at confirmation time would leave a host
race between checking and deleting. A safe solution requires documented
Flame API behavior, stable marker identity semantics, independent
Selection validation and a testable failure/restore policy on a
disposable Project. Avoid assuming that `PyMarker` Python proxy
identity remains stable across calls or that Flame offers a transaction.

**Do not turn an advisory count into deletion permission.** In
particular, a selected `PyReel` with no direct Clip/Sequence marker
targets must not be treated as deletable merely by type name.

## Evidence

- [Autodesk Flame 2026 Custom UI Actions](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Python-Hooks-Reference/Flame_API_Python_Hooks_Reference_Custom_UI_Actions_html.html)
  documents a tuple of selected objects supplied to
  `isVisible`, `isEnabled` and `execute`. It does **not**
  guarantee the same objects across phases.
- [Autodesk Flame 2026 Python API Cookbook](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Python-API/Python-API-Examples/Flame_API_Python_API_Python_API_Examples_Flame_API_Cookbook_html.html)
  demonstrates `PyClip.markers` access; it does not establish a
  safe transactional bulk-marker-delete mechanism.
- Internal code basis: `rename.py`, `markers.py`,
  `actions/rename_action.py`, `actions/delete_markers_action.py`,
  and the opt-in
  [built-in Selection profile review](2026_BUILTIN_SELECTION_PROFILES.md).

## Isolated validation and release gates

`tests/test_action_plan_safety_review.py` contains **29 new unit
test methods**: model shape/status consistency, duplicate host object
identities and attribute wrappers, proposed-name conflicts, marker
aliases across target plans, no-op plans, safe redaction, and a complete
absence of host API/file operations.

In a disposable Python **3.13.5** fixture-only tree, **29/29** new
methods passed; the **86-test** combined selection-contract +
built-in profiles + plan-audit subset finished with **85 passes
and 1 skipped** ActionRegistry comparison, because the local fixture
tree does not include full Public source. Both new files parse under
Python 3.11 grammar. [GitHub Actions CI 45197667828](https://github.com/71233/dg-python-scripts/actions/runs/45197667828)
**passed** on Ubuntu 24.04 / Python **3.11**: **132/132 Public
unittest cases** (29 new + 103 existing), editable package installation
and wheel build all succeeded. No skipped tests were reported.
This validates the current Public dataclasses and ActionRegistry
integration in Linux CI, **not** the actual Flame 2026.2.3 host.

**Do not** wire these reviews into `hooks.py`, existing
`SelectionBroker`, menus, Rename UI or Marker deletion yet. Keep
[Public PR #7](https://github.com/71233/dg-python-scripts/pull/7)
Draft and separate from [deployment preflight PR #6](https://github.com/71233/dg-python-scripts/pull/6).
Flame 2026.2.3 bundled **Python 3.11.5**, actual callback and
object behavior, symlink/Hook layout, and recovery have not been
verified on macOS.

Only the production Mac is available; no independent disposable
Flame instance exists. **G3 isolated Flame and G4 deployment
remain NO-GO**. Do not install/unlink Hooks, change privileges,
Reset/Import Flame Setup Profiles, merge, or test destructive
operations on production objects.
