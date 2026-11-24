# G2 broker / registry / menu / hook audit — 2026-11-24

Status: isolated Python models only; Draft, unmerged, undeployed. G3/G4 NO-GO.

## 2026-11-24 — malformed selections and same-context host names (G2 only)

Flame 2026's [Custom UI Actions specification](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Python-Hooks-Reference/Flame_API_Python_Hooks_Reference_Custom_UI_Actions_html.html)
documents tuple callback inputs, action names intended to be unique,
and a shortcut for each custom action. It does not specify whether
different hook contexts share a single name namespace, case folding,
or how custom actions collide with installed hooks and shortcuts.

The existing broker coerced arbitrary iterables to tuples, treating
conversion exceptions as empty selections. A malformed execute could
therefore select an earlier unselected snapshot; duplicate identities
also made set/length matching ambiguous. The Draft accepts only plain
tuples and plain lists (the latter retained as local compatibility,
not a documented Flame payload). It rejects primitives and repeated
Python identities before accessing selected metadata or dispatching
the action. It shares the primitive classifier with the opt-in
selection reviewer, not the reviewer's full contract, size cap,
context/action profiles or live wiring. Invalid predicate input follows
the existing exception block; invalid execute input consumes its
snapshot and raises without calling the Action. A later fresh valid
execute remains allowed unless a predicate failure is outstanding.
No arbitrary iterable or tuple/list subclass is consumed. Normal
empty selections, distinct objects and legacy priority remain intact.

ActionRegistry now rejects exact duplicate host names among distinct
Actions in an overlapping context, regardless of menu hierarchy or
whether the name comes from caption or flame_name. Both single and
batch registration validate before mutation; the existing extension
loader rejects an entire conflicting extension and continues. Names,
captions, existing shortcut identities and cross-context registration
are not rewritten. This does not establish global shortcut uniqueness,
case/Unicode normalization, or the namespace of third-party hooks.
Current Public built-ins and the recorded Internal diagnostic action
have distinct host names; actual integration with this Draft remains
unverified.

Fifteen additional synthetic regressions cover malformed/duplicate
inputs, failure recovery, no arbitrary iteration or instance access
during validation, identity order, plain-list/empty compatibility,
same-context name overlap, batch atomicity and extension isolation.
The previous tests are retained. No actual Flame callback, registered
shortcut or production environment was exercised. G3/G4 NO-GO.

## 2026-11-24 — experimental predicate exception policy (G2 only)

The old wrappers capture selection before evaluating isVisible/isEnabled.
A predicate exception or failing truth conversion leaves the failed
snapshot available to execute; deleting it alone would select the
execute argument instead, which can be a different target. The Draft
now invalidates the snapshot on an escaping exception, re-raises the
original error and blocks resolve/execute for that Action/context until
**each failed predicate phase subsequently returns True**. A False
result or the other phase's True/default cannot clear that phase's
failure. While a predicate is evaluating, same-key nested evaluation
and execution are rejected before execute selection conversion. These
guards address synchronous re-entry, not threads or arbitrary host
event ordering. A normal, caught nested rejection does not by itself
make the enclosing successful predicate fail.

The block is not one-shot: repeated execute calls cannot fall through
to another selection. Successful recovery resumes the existing
2025-derived priority and one-shot snapshot consumption. A False
result without an outstanding exception retains the old behavior,
including the fact that False is not a dispatch authorization barrier.
An absent predicate still defaults to True in its own phase. No
predicate is re-run during execute, no TTL or host imports are added,
and the opt-in 2026 selection contract stays disconnected.

Autodesk 2026 documents callable enable/visibility and execute tuple
arguments, but not the failure/shortcut ordering needed to prove this
policy in a live host. This is a conservative DGpy-specific experiment,
not a host contract. A legitimate shortcut might remain blocked if
Flame never invokes the failed phase again; how exceptions appear in
Flame is also unverified. Snapshot freshness after recovery, normal
False handling, object identity and cross-thread/host re-entry remain
open. Do not deploy, merge, or use the production Mac. G3/G4 NO-GO.

Twelve synthetic tests cover exceptions in both phases, truth conversion,
repeated execute, phase-specific recovery, isolation, menu rebuild,
synchronous re-entry, preserved normal False and direct execution.
The first ten were committed separately against the old implementation
for a controlled red run; two additional phase-specific cases accompany
the implementation. The original 2025 SelectionBroker tests are unchanged.

## Evidence and preserved behavior

Audited Public PR #7 base HEAD `003816a5538785640d81ad21c9e133039682e31e`
and Internal PR #3 `13d73a1bc4244bf155dbc4076b65be8f8c272cea`.
Public #6 stays independent at `edcc1aec0becd81bf9a6d3331b75f2a69fa876b6`.
No user checkout or production host was inspected; current local dirty state is unknown.

Official [Flame 2026 Custom UI Actions](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Python-Hooks-Reference/Flame_API_Python_Hooks_Reference_Custom_UI_Actions_html.html)
documents seven entry points, tuple arguments for isVisible/isEnabled/execute,
and action names intended to be unique. It does not establish equality,
ordering or freshness across callbacks, stable proxy identity, or execution
authorization from a predicate. Multiple hook definitions are combined;
later definitions may override earlier conflicts.

Existing implementation: SelectionBroker keys by context and Action identity,
keeps the latest predicate snapshot and consumes it before invoking execute.
It preserves predicate ordering for matching members, prefers a captured
explicit unselected target on mismatch, otherwise uses execute selection.
The three original SelectionBrokerTests in tests/test_core.py remain unchanged:
unselected context target wins, selected stale snapshot falls back, same members
preserve order. These encode recorded 2025.2.7 behavior, not new 2026 evidence.
The opt-in selection_contract remains disconnected.

## Minimal exception-boundary repair

A synthetic selected attribute can raise while resolving its get_value attribute
(before calling it). That lookup was outside the existing try block, so predicate
capture could raise and leave an older snapshot stored. Move only that lookup
inside the existing selected-read try block. An unavailable lookup now means
selected state unknown (None), as existing getter-call and boolean-conversion
failures already do. Mismatched execute then follows the existing fallback.
No new predicate re-evaluation, host reads, TTL, selection preference, Hook wiring,
or registry/menu behavior is introduced.

## Independent regressions

tests/test_dispatch_safety_2026.py adds 13 unittest cases using fake objects and
temporary mocks: getter metadata failures (including older unselected snapshot),
Action/context isolation, latest predicate, one-shot consumption on action error,
unknown-state fallback, current no-predicate-recheck behavior, atomic duplicate
and iterator failures, menu dict copying with callback reuse, failed registry
initialization/retry, all seven context delegations and bootstrap error containment.
Existing tests are not rewritten. CI must confirm counts and wheel build;
no host or local Python runtime verification is claimed here.

## Remaining risks / G3 gates

- Unselected snapshots can remain stale if no later predicate replaces them.
  Snapshot age and host object lifetime are unknown; one-shot is not freshness.
- At the prior audit stage, False or exceptions did not block execute.
  The experimental exception guard above addresses escaping exceptions;
  normal False still does not authorize or forbid dispatch. Destructive
  actions need their own validation, and actual host ordering is unresolved.
- The current Draft rejects duplicate identities and malformed callback
  shapes before resolution (see above); identity does not authenticate host
  objects or distinguish two different proxies for the same host object.
- Exact same-context host names are rejected within the DGpy registry.
  Cross-context, external modules, group names, shortcut naming and actual
  load ordering still require isolated host verification.
- Cached bindings and process registry retain references for the process lifetime.
  No unload/reload, concurrent/reentrant predicate capture, proxy validity,
  anonymous hierarchy/waitCursor/separator support or Qt lifecycle is proved
  by these tests. Bootstrap catches menu-building failures, not later callbacks.

Next: assess remaining malformed/duplicate selection and host-name
collision risks without assuming host semantics; obtain an independent
disposable Flame 2026 environment before validating callback ordering,
exception recovery, hierarchy/shortcuts and proxy lifetime.
Production Mac, Hook paths, Profile/settings, permissions, local checkouts and
sources/ are untouched. No installation, merge, reset or force update.

## Verified CI and legacy cross-check

[CI 45309681465](https://github.com/71233/dg-python-scripts/actions/runs/45309681465)
for head `e56116664eeaeed03cc619bf3450e24b999e70e4`: Ubuntu 24.04.5,
CPython 3.11.18, **197/197 unittest cases**, including all 13 new cases and
the original three SelectionBroker tests; editable install and wheel succeeded.
The job checked out GitHub's synthetic PR merge ref
`308c6f4b93b93e5ba9325e636b6e97814e957f68`
(head e561166 into unchanged main 1764a9f), not a user checkout or an actual merge.
No pre-fix test run was performed; the defect explanation is source analysis
plus passing fixed-code regression cases, not a measured red/green comparison.

Public 2025 Draft #4 at `85568fd56bfa73b4e29d871ffdb59378dcb977a2`
has identical tests/test_core.py content to the pre-audit #7 file.
Its docs/FLAME_NOTES.md records the same legacy selection preference as
an existing-code contract and distinguishes user reports from new measurements.
Those records and tests were read only; neither legacy PR was changed.
Public #7 has no docs/DEVELOPMENT.md or docs/FLAME_NOTES.md; current 2026
development and host notes are in Internal #3. No new 2025/2026 host
observation was made. G3/G4 remain NO-GO.
