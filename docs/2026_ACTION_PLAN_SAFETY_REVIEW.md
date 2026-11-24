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

## 2026-11-24 — Rename forward guards and final verification (Draft only)

The previous global preflight and per-setter read-back did not cover
changes between targets. Before each temporary write, compare the
captured attribute to its original name; before each final write,
compare it to that row's generated temporary name. After all final
writes, read every ready row and compare with its proposed name before
returning success. Mismatch or unavailable read in any new guard raises
a private subclass of RenameApplyError. **No further setters or
automatic rollback are invoked after that detection**, because the
unexpected/unknown state might include an external edit. Earlier
temporary or final names may remain; the existing failure UI warns of
uncertain recovery and closes. An empty rollback_errors tuple on this
path does not mean restoration occurred. The old global stale-preview
check and existing compensation for setter/read-back failures remain.

Eight synthetic regression cases exercise original-name drift after
global preflight, later-row drift/read failure, temporary-name drift
before final writes, late drift/read failure at final verification,
and healthy writes. No host lock, stable attribute identity,
atomic compare-and-set, atomic final snapshot, concurrent recovery
or verified real Flame behavior is claimed. Changes after a guard or
between final reads can still escape detection. No unrelated rows
are inspected; existing rollback hazards and actual G3 host behavior
remain unresolved. G3/G4 NO-GO.

## 2026-11-24 — Rename rollback verification and failure lockout (Draft only)

Individual restoration writes were read back, but a later setter could
change an already restored row without adding a rollback issue. After
either temporary-stage or final-stage failure, the existing compensation
algorithm now performs one **read-only pass over all ready rows** to
compare their current names with the original preview. Mismatches and
read errors are appended to existing rollback issues; no second recovery
attempt is added. This includes ready rows not yet written when a
temporary setter fails. It does not check unrelated objects or guarantee
an atomic snapshot, stable host proxies, or successful restoration.

The previous Rename dialog unconditionally rebuilt its preview after any
apply error, even when a temporary name remained. The apply callback now
consumes the plan and blocks re-entry and refresh before applying.
A stale pre-write error retains the ability to review a refreshed preview.
For any other RenameApplyError it explains possible changed/temporary
names and uncertain restoration, preserves error details, and closes
the dialog without automatic re-preview or another apply. This is a
conservative UI stop, not a persistent cross-dialog host lock.
Eight synthetic regression cases cover the post-rollback audit,
unattempted rows, read failures, dialog failure lockout, stale preview
and healthy apply. Actual Qt event handling, Flame attribute lifetime,
concurrency and recovery still require G3. No Hook wiring or deployment.

## 2026-11-24 — honest Marker failure diagnostics (Draft only)

The existing error dialog previously presented `MarkerApplyError.deleted`
as an exact "Deleted before failure" count, even after an unreadable
collection or an insertion that hid a real deletion in the net count.
The dialog now distinguishes a `StaleMarkerDeleteError` (DGpy made no
delete calls) from other apply failures (the deletion count is not
reliably verified; markers may already have changed or been deleted;
no automatic restoration was attempted; inspect the affected targets).
It omits the numeric estimate in the failure dialog, retains the original
error details, and makes no change to delete sequencing, success
notifications or cancellation. The legacy exception field remains
available for compatibility, not as an authenticated count.

The existing stale-dialog test was updated and seven additional fake-host
UI regression cases cover rejection before mutation, mutation then
exception, insertion masking a removal, unreadable remainder, unexpected
multi-deletion, healthy success and cancel. These exercise the existing
dialog entry point using a mock Flame module; they are not live UI/Flame
observations. G3/G4 remain NO-GO; no production deployment or restore.

## 2026-11-24 — within-target Marker recheck (Draft only)

**Further G2 failure injection:** The previous version rechecked each
Clip/Sequence *before* processing its captured marker list, but
performed subsequent callbacks on the **same target** without another
snapshot check. A callback that silently removed a different marker,
replaced or inserted a marker, or left the first marker unchanged
could therefore still trigger a later delete with a stale reference.

Six disposable regression cases were added to
`tests/test_action_failure_injection_2026.py` (23 → **29**). On the
original implementation,
[GitHub CI 45305286334](https://github.com/71233/dg-python-scripts/actions/runs/45305286334)
ran 161 tests and had **5 expected regression failures**:
second callbacks were issued after same-target changes (or an
unreadable collection), and a callback that removed both markers
could even produce an apparent success. The healthy three-marker case
passed. This was a **controlled red regression run**, not evidence of
Flame 2026.2.3 behavior.

**Draft-only fix:** The existing
`markers.apply_delete_plan()` retains its all-target preflight and
per-target recheck. Now, **before each *subsequent* marker callback
on the same target**, it re-reads the current collection and compares
its ordered Python object identities against the **unprocessed suffix**
of the original captured snapshot. A changed or unreadable collection
raises `MarkerApplyError` and **no further delete callback is made**.
The first callback for each target is preceded by the existing
per-target check. Healthy multiple-marker operations still follow
their previous execution path.

[GitHub CI 45305365570](https://github.com/71233/dg-python-scripts/actions/runs/45305365570)
subsequently **passed 161/161 Public unittest cases** on Ubuntu 24.04
/ Python **3.11**, including all six new cases, editable installation
and wheel build. Tests use synthetic fake Clip/Marker objects, not
the Flame runtime.

**Limits and unresolved G3 checks:**

- The first callback may already have deleted or changed markers
  when a later check stops the plan. **No undo or restoration** is
  performed or implied.
- Another host operation could change a marker between the
  re-read and the next delete callback. The new checks do **not**
  make deletion atomic, protect against overlapping writes or
  establish an official Flame transaction mechanism.
- `PyMarker` object identity on repeated `PyClip.markers` reads is
  **not documented here as stable**. The conservative identity
  comparison can reject valid plans when proxies are re-created;
  more reads make that a more prominent compatibility gate.
  Do not replace identity with guessed names, positions or timestamps.
- `MarkerApplyError.deleted` is a **best-effort net count estimate**.
  A failed re-read may leave it at zero after a real deletion;
  insertion/replacement can also make the value misleading. The
  error dialog at that stage used that legacy field; the newer
  failure diagnostic above omits it. Treat it as a diagnostic,
  **not verified deletion or successful recovery**.

Actual Flame 2026.2.3 macOS/Python 3.11.5, Marker proxy lifetime,
concurrent edits and undo/recovery remain **unverified**. Do not
install or use this Draft on the only production Mac; G3/G4 remain
NO-GO. No Hook/Menu/SelectionBroker/UI wiring was introduced.

## 2026-11-24 — staged recheck and fail-fast Marker deletion (Draft-only)

**Motivation:** The original all-target validation stops stale previews
before any delete, but after the first callback it can no longer
guarantee later targets remain unchanged. The earlier implementation
also continued to issue delete calls for the rest of the captured
markers when a callback raised, even if the callback had partly
mutated its target.

A further **unmerged, synthetic-tested** change to
`src/dg_python_scripts/markers.py` keeps the all-target precheck
and adds two narrower stop rules:

1. **Before each target with captured markers**, re-read that target's
   marker collection and compare the ordered proxy identities with the
   captured snapshot. If a previous target's callback changed this
   later target, or it can no longer be read, raise
   `MarkerApplyError` and **do not delete markers from that target
   or any subsequent one**. This error is **not**
   `StaleMarkerDeleteError`: some earlier targets may already have
   been mutated.
2. **On the first delete callback exception**, stop immediately,
   perform a best-effort read-back of the current target to estimate
   the net removed count, and raise `MarkerApplyError`. Do **not**
   continue calling delete on subsequent captured markers or targets.
   Post-target read-back failure or markers remaining likewise stops
   further callbacks.

Five further synthetic cases exercise mutation/unreadability of a
later target, rejection before or after a marker was removed,
and re-created Python proxy objects. The existing tests now require
**fail-fast** behavior rather than accepting calls on later targets
after the first callback exception. These tests do not assert that
deleted markers were restored: the first target can remain partially
changed.

**Important limitations:** A Python read is not an atomic lock.
A host can change between a target's recheck and its next callback,
or change the **same** target during a callback. The result's
`deleted` remains a **best-effort net-length estimate**, not an
authoritative count of successful calls. The code deliberately
compares `is` identity rather than unverified marker properties:
Flame might return fresh `PyMarker` proxies on each access, causing
valid plans to fail closed. All such host semantics require a
separately isolated Flame 2026.2.3 validation before any rollout.

No new automatic retry, workaround using raw marker names/times,
hypothetical host transaction, undo or repair operation was added.
Neither `hooks.py` nor `SelectionBroker`, current menus, dialogs,
Qt or production Hook paths was changed.

## 2026-11-24 — late mutation, callback errors and rollback-failure diagnostics

A further isolated review of the **unmerged Draft** shows:

- **Marker callback exception after a successful mutation:** The prior
  `apply_delete_plan()` collected callback exceptions but only reported
  them when markers remained. A callback that removed the last marker
  *and then raised* could therefore return success, hiding an error.
  A disposable Python reproducer demonstrated this false-success path.
  The Draft-only fix now treats `remaining or delete_errors` as a
  failure, even when a read-back shows an empty marker collection.
  The caller receives `MarkerApplyError` through its existing UI
  error path; an exception does **not** imply the operation was undone.
- **Marker mutation *after* all-target preflight:** A test deliberately
  adds a marker to a later target inside the first delete callback,
  after all preliminary snapshots were checked. The operation still
  may partially delete captured markers before returning an error.
  This is a **documented, unresolved TOCTOU race**. There is no
  general-purpose atomic bulk-delete guarantee from the Python check.
- **Rename final-stage rollback:** Two additional fixtures cover
  restoration after a final-name write error and an explicit rejection
  of restoration. The rejected restoration remains visibly incomplete,
  but `RenameApplyError.rollback_errors` records the failed
  compensation instead of declaring a successful rename.

Five new unit methods extend
`tests/test_action_failure_injection_2026.py` from **13 to 18**.
[GitHub Actions run 45303403657](https://github.com/71233/dg-python-scripts/actions/runs/45303403657)
**passed 150/150 Public unit tests** on Ubuntu 24.04 / Python 3.11,
along with editable installation and wheel build. No production
Flame object, user Hook or production setup was accessed.

**Result semantics:** `MarkerApplyError.deleted` comes from the
preexisting *net-count difference* between captured and remaining
collections. Concurrent insertions, proxy re-instantiation and
partial callback side effects can make this an **unreliable estimate**
of exactly how many delete calls succeeded. It is diagnostic, not
proof that every deleted object was known or recoverable.

**G3 remains NO-GO.** Actual Flame 2026.2.3 Python 3.11.5/macOS
proxy identity, host delete/rollback semantics, caller Selection,
and safe restoration after partially destructive operations are
unverified. No redesign can honestly claim a transaction without
an independently validated host mechanism. Keep both Public Draft
PRs unmerged and do not attempt destructive probes on the only
production Mac.

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
