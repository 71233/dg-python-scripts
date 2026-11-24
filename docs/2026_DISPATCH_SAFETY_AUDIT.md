# G2 broker / registry / menu / hook audit — 2026-11-24

Status: isolated Python models only; Draft, unmerged, undeployed. G3/G4 NO-GO.

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
- Predicates returning False or raising are not an execution authorization barrier.
  Existing dispatch does not re-run them; an error after capture can leave a
  snapshot. Destructive action callbacks need their own validation. Changing
  this policy requires separate evidence and compatibility review.
- _same_members uses Python identity sets plus length, so duplicate multiplicity
  is not distinguished; equality does not authenticate host identity. Unknown
  iterables are coerced; failed iteration becomes empty. These remain legacy
  behavior, not a validated 2026 contract.
- Registry rejects duplicate internal IDs atomically for normal Action batches,
  but does not enforce host-name uniqueness. Across modules/groups, shortcut
  naming and load ordering still require isolated host verification.
- Cached bindings and process registry retain references for the process lifetime.
  No unload/reload, concurrent/reentrant predicate capture, proxy validity,
  anonymous hierarchy/waitCursor/separator support or Qt lifecycle is proved
  by these tests. Bootstrap catches menu-building failures, not later callbacks.

Next: separately evaluate predicate failure snapshot policy with synthetic tests
and compatibility evidence; obtain an independent disposable Flame 2026 environment
before investigating actual callbacks, hierarchy/shortcuts and proxy lifetime.
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
