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
Qt, filesystem operations or any Hook. They are **not invoked by the
current menus**, so existing runtime behavior remains unchanged.

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

**Potential failure point found by static review:** during temporary
renaming, an object is added to `temporary_rows` *after*
`_write_exact()` returns. If `set_value()` partially changes the
host object but read-back then fails, that object might not be included
in the first rollback list. Confirm and address this with disposable
failure-injection fixtures **before** relying on transactional rollback.
The new structural reviewer does not fix the write path.

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

**Potential failure point found by static review:** the current
`markers.apply_delete_plan()` loops over the markers captured during
preview and validates remaining markers **after** issuing deletions.
A target collection may change between preview and confirmation.
It does not first compare every live marker collection with the
snapshot before the **first** deletion. A stale plan may therefore
cause partial deletion before a mismatch is noticed. The new
structural reviewer does not solve this time-of-check/time-of-use gap.

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
Python 3.11 grammar. The full GitHub Python 3.11 CI against actual
Public dataclasses and ActionRegistry **must be checked separately**.

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
