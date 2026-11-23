# Flame 2026.2.3 — generation-bound v2 anchor preview (NO APPLY)

**Status: experimental and non-operational.** This is a read-only, pure-Python
cryptographic *consistency model*, not a production credential store, Hook
installer, rotation service, or recovery tool. It does not import `flame`,
Qt/PySide, touch any Hook directory, read/write a journal, sign records or
generate/store/change secret keys.

Public API: `V2Anchor`, `V2KeyState`, `V2Evidence`, `V2Review`,
`assess_v2_anchor_preview()` in
`src/dg_python_scripts/deployment/anchor_v2_review.py`.
The v1 [HMAC anchor review](2026_HOOK_HMAC_ANCHOR_REVIEW.md) and
[key-custody preview](2026_KEY_CUSTODY_RECOVERY_PREVIEW.md) remain unchanged
and fail closed on new key generations. **No automatic v1→v2 conversion or
fallback exists.**

## v2 versus v1

The v1 HMAC anchor binds scope, key identity, transaction identity,
event count, revision and journal tip, **but not key generation**.
v1 therefore rejects key generation 2+.

The v2 experimental HMAC explicitly includes `key_generation` **and an
opaque `deployment_id`** in the authenticated bytes and uses a
**distinct protocol and MAC domain**.
The review can test generations 1, 2 and later values only when the
same generation is asserted by an *independently protected* source.
A v1 anchor or v1 MAC must not be silently accepted by the v2 verifier.

The bounded journal event format remains the existing v1 **in-memory**
SHA-256 chain for now. This is **not** a claim that v2 can safely load
old journals from disk or authenticate any preexisting real DGpy deployment.

## Canonical HMAC v2 fixture format

`V2Anchor` fields, in their canonical order:

```text
protocol, flame_version, scope, deployment_id, transaction_id,
key_id, key_generation, revision, event_count, terminal_state, tip_sha256
```

The `mac_sha256` field is excluded from the input. Test fixtures
serialize the listed fields as a JSON array using ASCII encoding with
`ensure_ascii=True` and separators `(",", ":")`, prepend the exact
domain separator `b"DGpy Hook Anchor HMAC-SHA256 v2\\n"`, and compute
HMAC-SHA256 with a **public deterministic test-only** 32-byte fixture key.
The production reviewer only **verifies** the MAC; it does not sign.

`protocol` must be `DGpy-Hook-Anchor-v2`, `flame_version` exactly
`2026.2.3`, scope `user` or `shared`, a validated ASCII
`deployment_id` (1–64 characters, no raw paths), and positive integral
generation (1 through 2³¹−1). Existing simplified journal semantics permit only
`ACTIVE` (revision 1, 3 events) or `DISABLED` (revision 2, 5 events).
The format is provisional, not an approved production wire protocol.

## Ordering and STOP conditions

`assess_v2_anchor_preview()` first requires *separately established*
attestations that the key origin, current revocation status, current
checkpoint, anchor origin, and **isolated disposable environment** are
all independently reviewed. It requires trusted expected scope,
**deployment identity**, transaction ID, key ID, generation, revision
**and tip digest**.

It rejects unknown, retired or revoked key state; mismatched identity,
generation, deployment identity, revision, tip; wrong protocol/version;
invalid input types;
old/modified MACs; inconsistent, incomplete or altered event chains.
The v2 data classes are exact-type checked to reject hostile subclasses.
It only inspects the event collection **after** all the metadata and HMAC
checks pass. A problem yields `BLOCKED` with
`MANUAL_RECONCILIATION`, **never automatic retry, unlink or restoration**.
A matching model yields `PREVIEW_ONLY` with `NO_CHANGE`, **not an
authorization**.

No path, transaction ID, key, anchor MAC or private record is included
in the structured findings.

## Identity-binding review and independent authority requirements

A code review found that scope alone (`user` or `shared`) did not
distinguish two separate Hook deployments. The experimental v2
**now also requires an independently established, opaque
`deployment_id`** in `V2Anchor`, `V2KeyState`, and
`V2Evidence.expected_deployment_id`, and includes it inside the HMAC.

When the independent expected deployment ID, key state and signed anchor
disagree, the result is `BLOCKED`. Replacing the ID in all three
objects without recomputing the MAC also blocks. The same key ID and
transaction ID on two *different* fixture deployment IDs produce
distinct MACs. The v2 test suite includes ten new regression cases.

**This is not an implementation of deployment identity issuance.**
The caller must establish uniqueness and provenance independently, and
must prove that an opaque ID refers to the correct effective
machine, Flame User/profile, Hook root, destination and source revision.
This reviewer cannot determine those facts, and a forged or reused
independent ID can still make unrelated environments appear equivalent.
Raw usernames, device names, filesystem paths and production records
must not be embedded in IDs or committed to Public.

The earlier *unreleased* experimental v2 canonical layout without
`deployment_id` is intentionally **no longer accepted**. This Draft
PR is not a stable persisted-record specification; before any release,
the wire protocol/version must be reviewed, frozen and test-vector
verified separately. Do not silently fall back to the older v2 layout.

A deployable trust boundary would require **all three independent
proofs**, not just boolean flags: (1) a well-defined issuer and
protected lifecycle for key/deployment identities, (2) a separately
authenticated, monotonic current generation/revision/tip checkpoint,
and (3) evidence that those identities match the actual effective
Flame Hook search roots and installed source. None currently exists.
`PREVIEW_ONLY` is a *consistency result*, never a release gate.

## Trust limitations and non-goals

- The `V2KeyState` and `V2Evidence` values are **untrusted inputs**.
  Their `*_verified=True` flags are claims, not a trusted service.
  The verifier does **not** authenticate the issuing key manager,
  verify a revocation list, or prove a monotonic checkpoint's freshness.
- V2 binds generation cryptographically, but **does not generate, rotate,
  revoke, select or store any keys**, nor ensure different generations
  actually use independent secrets or that key IDs cannot be reused.
- A former signed anchor cannot pass against a genuinely independent newer
  revision/tip. However, if an attacker controls the key **and** the
  purported external checkpoint/attestations, coherent forged records
  can pass. A test intentionally demonstrates this limitation.
- Even a valid MAC does not show that Flame loaded any Hook or that a
  symlink was installed, removed or restored. A read-only snapshot cannot
  eliminate races or establish filesystem ownership.
- The user's only macOS Flame 2026.2.3 workstation is **production**.
  No Hook or Profile testing should occur there without a separately
  proven isolated environment. User/Shared Hook roots previously measured
  as mode 0777 are still unsafe; never auto-chmod.
- Full key custody, independent attested anti-replay storage, key-reuse
  prevention, crash-safe transactions, a recovery operator workflow and
  isolated real-Flame integration remain **G3/G4 NO-GO**.

## Evidence

The baseline v2 fixture suite had 63 tests. The identity-binding review
added ten new cases: **73/73** v2 tests passed on disposable Python
3.13.5, and **196/196** of the corresponding locally available
preflight/journal/lifecycle/v2 fixtures passed. The changed source
and tests parse under Python 3.11 grammar.

The updated [CI run 45176255751](https://github.com/71233/dg-python-scripts/actions/runs/45176255751)
**passed** on Ubuntu 24.04 / Python 3.11 with **340/340 Public
unit tests**, editable installation and wheel build. This latest
run includes the ten identity-binding tests. Neither local
tests nor Linux CI establishes runtime compatibility with Flame's
exact bundled Python 3.11.5 on macOS.

See [2026 Hook preflight](2026_HOOK_PREFLIGHT.md) and
[NO-APPLY lifecycle design](2026_HOOK_LIFECYCLE_DESIGN.md).
