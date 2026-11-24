# Flame 2026 — built-in Action Selection profile previews (NO HOST USE)

## Captured Rename / MarkerDelete plan audit (read-only, not wired)

The separate [Action plan safety review](2026_ACTION_PLAN_SAFETY_REVIEW.md)
checks structural contradictions in *already captured* `RenamePlan` and
`MarkerDeletePlan` snapshots without reading host object properties
or executing an action. It blocks duplicate identities, duplicate marker
references, invalid names, ambiguous requested rename collisions and
inconsistent plan rows. **It cannot prove marker freshness, namespace
ownership, successful writes or rollback.** Every matching result still
requires a live host recheck; marker deletion also requires explicit
operator confirmation.

**Failure-injection follow-up:** The two prior static risks were
reproduced using disposable Python objects. [The Action failure
review](2026_ACTION_PLAN_SAFETY_REVIEW.md) now documents **minimal
Draft-only runtime fixes** in `rename.py` (attempted-row rollback)
and `markers.py` (check every captured marker collection before
the first delete callback). These are **not Flame 2026.2.3
host-validated** and do not provide atomic rollback or host-safe
bulk deletion. The advisory plan auditor itself is **still not wired
to the current UI or live Host**.

**Status: isolated G2 model only. No Action dispatch, Flame/Qt import, profile mutation, Hook installation or production Mac test.** This companion to the [2026 Hook/Selection callback contract](2026_HOOK_SELECTION_CONTRACT.md) expresses **existing Public DGpy built-in Action requirements** as *advisory* structural policies. It is **not** used by `hooks.py`, `actions/menu.py`, `SelectionBroker`, the bootstrap, or any running Flame process.

## Reviewed source of truth

The existing Public `src/dg_python_scripts/actions/main_menu.py`, `rename_action.py`, `delete_markers_action.py`, `registry.py`, `rename.py` and `markers.py` remain unchanged. The new `BUILTIN_SELECTION_PROFILES` table is deliberately limited to the three registered built-in Action IDs:

| Existing Action | Existing context(s) | G2 Selection preview | Important missing proof |
| --- | --- | --- | --- |
| `dgpy.about` | `main_menu` | Zero or more callback objects permitted; Selection is not used by the About action | Does not prove menu/Qt availability |
| `dgpy.rename` | `media_panel`, `timeline`, `batch`, `action` | Requires at least one structurally valid selected object; allows multiple and mixed objects; **no class-name allowlist** | Existing `rename.probe_target()` checks `name.get_value()` / `name.set_value()` and rejects `PyBatchIteration`; the new preview deliberately performs **no such property access** |
| `dgpy.delete_markers` | `media_panel` | Requires at least one object with **type-name hint** `PyClip`, `PySequence` or `PyReel`; mixed unrelated objects are not discarded | Existing `markers.collect_marker_targets()` / `build_delete_plan()` must discover actual direct Clip/Sequence targets and inspect markers; type name alone cannot prove an object is a Flame type, contains markers or can safely be modified |

The static contexts are checked in an isolated test **against the actual existing `register_builtin_actions(ActionRegistry)` output**, to detect drift if Action registration changes. The table is **not a second Action Registry**, and **does not introduce new menu items**. Extension/third-party action IDs are intentionally unsupported. The `dgpy.delete_markers` path is potentially destructive: no preview here authorizes deletion.

## Contract

`actions/builtin_selection_profiles.py` exports:

- `BuiltinSelectionProfile` and immutable `BUILTIN_SELECTION_PROFILES`, mapping known Action IDs to their existing contexts and structural limits.
- `inspect_builtin_selection(action_id=..., hook_name=..., phase=..., selection=...)` which invokes the existing **opt-in** `inspect_hook_selection()`, but only for contexts the particular Action already registers.
- `BuiltinSelectionReview` with generic finding codes, callback context/phase, total selection count, an optional **unverified class-name candidate count**, and a `requires_host_capability_check` flag. It holds **no Flame object references**.

An unknown Action, invalid Hook, wrong registered context, malformed callback argument, empty Selection for Rename/Delete Markers, duplicate identity, or Delete Markers with no named candidate returns `BLOCKED / MANUAL_RECONCILIATION`. A structurally matching callback returns `PREVIEW_ONLY / NO_CHANGE`, **never** `EXECUTE`, `ENABLED`, `SAFE_TO_DELETE` or `SAFE_TO_RENAME`.

**No object properties are read**: the code does not inspect `.selected`, `.name`, `.markers`, `.clips`, `.sequences`, `get_value()`, `set_value()`, or call an Action. A class named `PyClip` can be fabricated in ordinary Python. Passing a type hint therefore only says the candidate *looks like* one current target class by name; it is **not validation of Flame object identity, capabilities or permission**.

## 2026 API basis and limitations

[Autodesk Flame 2026 Custom UI Actions](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Python-Hooks-Reference/Flame_API_Python_Hooks_Reference_Custom_UI_Actions_html.html) documents the seven Custom UI Actions Hook points, the tuple parameter to `isVisible`, `isEnabled` and `execute`, and keyboard shortcut availability. It does **not** establish that callback Selection is identical across phases, or that DGpy's Flame **2025.2.7-observed** predicate/execute heuristic in `SelectionBroker` is correct for **2026.2.3**.

Each phase is therefore reviewed independently; no menu predicate snapshot is copied into `execute`. The strict exact-tuple rule comes from the proposed G2 base contract and must be checked on the target Flame version. No global selection fallback, object-type assumption or auto-adapter is introduced.

## Verification

In a disposable Python **3.13.5** container, **32** new test methods were run, alongside the existing **25** Selection contract tests. The local lightweight fixture tree did not contain the full preexisting Action Registry, so the one test that imports and compares real registrations was **skipped there**; the local report was **57 tests, 1 skip, 0 failures**. Both new Python files parse under the Python **3.11 grammar**.

[GitHub Actions CI run 45194804878](https://github.com/71233/dg-python-scripts/actions/runs/45194804878) **passed** on Ubuntu 24.04 / Python 3.11 with **103/103 Public unittest cases** (46 existing + 25 callback-contract + 32 new built-in policy tests), editable package install and wheel build. This run included the real ActionRegistry registration-consistency test and reported **no skips**. Do **not** claim macOS Flame runtime, actual callback behavior, host object capability or destructive-operation safety from Linux CI.

## Remaining gates

1. Keep Public [Draft PR #7](https://github.com/71233/dg-python-scripts/pull/7) separate from [Draft PR #6](https://github.com/71233/dg-python-scripts/pull/6), which concerns Hook deployment and recovery safety. Do not merge either yet.
2. Only a production macOS Flame **2026.2.3** workstation is available; there is no separately isolated Flame instance. Do not alter the workstation, production Hooks, menu, profile, permissions, install path or settings to test these models.
3. When an isolated Flame instance is available, establish actual callback object types for Media Panel/Timeline/Batch/Action; Selection changes between predicates and execution; the behavior of no selection, Reel right-click and keyboard shortcuts. Distinguish observed behavior from Autodesk's documented tuple contract.
4. Revisit Rename object capability and the destructive Delete Markers path **after** host verification, with explicit confirmation and error handling. An ordinary test object named `PyReel` with no children must **not** be interpreted as a deletable target.

**Production Hook wiring, automated execution and live modification remain NO-GO.**
