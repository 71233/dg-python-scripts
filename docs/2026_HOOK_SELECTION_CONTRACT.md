# Flame 2026 — opt-in Hook/Selection callback contract (NO HOST USE)

**Status: experimental, host-independent, and not connected to Flame.**

The new `dg_python_scripts.actions.selection_contract` is a small pure-Python
read-only reviewer of the arguments passed to a Flame Custom UI Action
callback. It never imports `flame`, PySide or Qt, calls a Hook, creates menus,
reads the global Media Panel/Timeline/Batch selection, stores predicate
snapshots, executes an action, or modifies any object or file.

## Basis and existing assets

**Autodesk 2026 official documentation:**
[Custom UI Actions](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Python-Hooks-Reference/Flame_API_Python_Hooks_Reference_Custom_UI_Actions_html.html)
documents the seven Custom UI Action entry points and specifies that each
`isVisible`, `isEnabled` and `execute` callable receives a **tuple of
selected Flame objects**. It does not establish that the three callbacks
always receive identical objects or that ordering/target-selection behavior
matches an earlier Flame release.

**Existing Public code:** `bootstrap/dgpy_bootstrap.py` and `hooks.py`
already define the seven entry points. `actions/registry.py` already models
the seven action contexts; `actions/menu.py` and `actions/selection.py`
provide menu and callback wiring. **Do not duplicate or replace them.**
The existing `SelectionBroker` intentionally contains a **2025.2.7
host-observed** heuristic: if the predicate captured an unselected object,
its selection may take precedence over the later execute callback. That
behavior has **not been tested** in Flame 2026.2.3 on macOS.

## What the proposed contract checks

`HOOK_TO_CONTEXT` has one fixed mapping per officially documented hook,
using the existing Public action-context names. The three callback phases
are `isVisible`, `isEnabled`, and `execute`.

`inspect_hook_selection(hook_name=..., phase=..., selection=...,
policy=..., expected_context=...)` checks:

- The Hook and callback names are known, and an optional independently
  expected context matches the Hook.
- The callback selection is an **exact built-in tuple**. This is a
  deliberately strict initial DGpy prototype based on the documented
  callback signature, **not a claim that every Flame build or custom
  wrapper always supplies an exact tuple**. A list, generator, or tuple
  subclass is rejected *without iteration*.
- No `None`, primitive scalar/container, or repeated **object identity**
  is present. No object comparison, conversion to `bool`, or access to
  `.name`, `.selected`, `get_value`, or other Flame instance attributes
  is performed.
- An action-specific `SelectionPolicy` may demand 1+ items, cap selection
  count at 256, refuse mixed **class names**, or allow particular class
  names. Default policy allows zero items and mixed opaque objects.
  Class names are **not** proof of a genuine Flame object and can be
  spoofed; only an independently confirmed Flame adapter can establish
  valid object type and capabilities.

The result `SelectionReview` uses only generic finding codes, the fixed
context/phase, and the number of accepted items. Its `items` field is
excluded from `repr` and must be consumed transiently; it is **never a
persisted/serialized snapshot**. Invalid inputs return empty `items`.

`PREVIEW_ONLY / NO_CHANGE` means **input structure passed this limited
model**, **not** that an action may be executed. Invalid/unsupported input
returns `BLOCKED / MANUAL_RECONCILIATION`. No action dispatch is included.

## Test evidence

`tests/test_selection_contract_2026.py` has **25 isolated unit tests**
covering seven Hook contexts, all three callback phases, empty and mixed
selections, per-action policies, invalid/missing items, infinite/hostile
iterables, tuple subclasses, duplicate identities, stale predicate vs
execute argument independence, non-mutation, no Flame/Qt import, and
redaction. All 25 passed with Python **3.13.5** in a disposable
container. Both new Python files parse with Python **3.11 grammar**.

[GitHub Actions run 45189586026](https://github.com/71233/dg-python-scripts/actions/runs/45189586026)
**passed** on Ubuntu 24.04 / Python 3.11, including **71/71 Public
unittest cases** (25 new + 46 existing), editable package installation
and a successful wheel build. The exact Flame-shipped **Python 3.11.5
on macOS** and real 2026 Hook/Selection behavior remain **unverified**.
This Linux CI is a package regression test, not a G3 host validation.

## G2 review of existing built-in Action-specific policies

The separate [Rename / Delete Markers / About Selection profile review](2026_BUILTIN_SELECTION_PROFILES.md)
adds a **host-free advisory** table for the three existing Public built-in
Actions, using this module's `inspect_hook_selection()` and the
current Action registration contexts. It does not wire an adapter, change
`SelectionBroker`, read Flame object properties or grant execution.
Delete Markers uses only untrusted class-name hints; Rename requires a
separate capability assessment. The 32 new test methods include a
full-repository ActionRegistry drift check; local lightweight fixtures
could not run that specific check, which is instead covered by Public CI.

## Gates and next step

- **Do not** switch `hooks.py`, the bootstrap, built-in menus, or the
  existing `SelectionBroker` to this prototype yet. No 2026 host behavior
  has been observed for predicate versus execution selections.
- In a separately approved **disposable** Flame 2026.2.3 environment,
  review each context with zero, single, multiple, mixed, and invalid
  selections; right-click targets, keyboard shortcuts, and predicate-to-
  execute changes. Capture **only anonymized observations**.
- Only after documenting the actual 2026 behavior should an adapter
  choose whether to use the passed execute tuple, predicate target,
  or another verified Host API. Do not guess from 2025 behavior.
- The user has **only a production Mac**. Production Hook installation,
  permissions changes, Flame Setup Profile Reset/Import, host probes,
  merges, and any changes to existing workflows remain **NO-GO**.

This proposal should be a **separate Draft PR from `main`**, not added to
the deployment-review Draft PR #6. The Internal development record should
link both PRs with their distinct scopes.
