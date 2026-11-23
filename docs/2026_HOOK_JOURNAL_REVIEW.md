# Flame 2026.2.3 — in-memory Hook journal consistency review (NO APPLY)

## Separate HMAC anchor verification prototype (isolated only)

The unkeyed `assess_journal_preview()` remains unchanged: it checks
the SHA-256 chain and an operator-asserted independent tip, **not**
cryptographic authentication. A **separate read-only**
[`assess_hmac_journal_preview()`](2026_HOOK_HMAC_ANCHOR_REVIEW.md)
now validates an HMAC-SHA256 anchor under an externally supplied key
**before** allowing the bounded event list to be reviewed.

The HMAC binds Flame version, User/Shared scope, key ID, transaction ID,
terminal state, number of events and revision as well as journal tip.
No key is created, persisted, retrieved from the OS or written to a
journal by DGpy. External key provenance, genuine anchor custody, trusted
anti-replay revision and an isolated test environment must be established
**independently**. Both `PREVIEW_ONLY` results are non-actionable and do
**not** authorize install, disable, unlink, restore or profile changes.

A compromised or substituted key/anchor authority can fabricate a
valid-looking chain. **Neither module claims real Hook state, actual
journal authenticity, or MAC-backed production recovery.**
See the companion HMAC design for explicit limits and test evidence.

**Status:** prototype for disposable fixtures only. It verifies a *bounded,
in-memory representation* of a proposed Hook transaction journal. It does
**not** open/write/authenticate a journal, start/stop Flame, install a Hook,
unlink a symlink, change permissions, or restore files. The production Mac is
not a test fixture. The implementation is pure Python and uses no Flame/Qt.

Source: `src/dg_python_scripts/deployment/journal_review.py`.
Public API: `JournalEvent`, `JournalReviewEvidence`, `JournalReview`, and
`assess_journal_preview()` in `dg_python_scripts.deployment`.

## Required independent evidence

All inputs default to unknown and a review fails closed. In order to inspect
events, the caller must independently establish and attest both:

- `independent_tip_verified=True`: the expected SHA-256 journal tip was
  obtained from an authenticated, protected **independent source**, not from
  the untrusted event list itself; and
- `isolated_environment_confirmed=True`: no production Flame Hook or private
  production data is involved.

The caller also supplies `expected_transaction_id` and
`expected_tip_sha256`. The code checks their syntax but **does not perform
cryptographic authentication**. Flags are operator attestations, not proof.
If either attestation is missing, the function does not iterate or inspect
`events` and returns sanitized `BLOCKED` findings. An unkeyed SHA-256 chain
can be recomputed by anyone who can edit the journal. It is only meaningful
against a tip protected independently of that journal.

## Proposed v1 event sequence (one Bootstrap transaction)

| Sequence index | Event type | Meaning in the **proposed** protocol |
| ---: | --- | --- |
| 0 | `INTENT` | Future installer durably recorded its intention; **not an actual install** |
| 1 | `LINK_CREATED` | Future installer recorded new managed link identity |
| 2 | `ACTIVE` | Future separate validation recorded active status |
| 3 | `DISABLE_INTENT` | Future operator recorded request to disable |
| 4 | `DISABLED` | Future separate validation recorded disabled status |

Only complete three-event `ACTIVE` or five-event `DISABLED` histories may
return `PREVIEW_ONLY`. One-, two-, and four-event partial histories are
`BLOCKED` for manual reconciliation. Event reordering, duplicates, missing
steps, invalid sequence numbers, transaction substitution, unknown types,
or more than five events are always `BLOCKED`.

**These states do not implement transitions**; they are hypothetical record
names for a future, separately reviewed installation system. The `ACTIVE`
label is not proof that Flame successfully loaded the Hook; `DISABLED` is
not proof that anyone has safely unlinked it.

## In-memory format and digest contract

Each frozen `JournalEvent` holds:

- zero-based `sequence` integer, one ASCII `transaction_id` (1–64 chars,
  alphanumeric first, then alphanumeric/underscore/hyphen), and `event_type`;
- opaque lowercase `payload_sha256` of an *external private evidence item*;
- lowercase `previous_sha256` and lowercase `event_sha256` (64 hex chars).

The first `previous_sha256` is 64 zeroes. For each event, the digest is:

```
sha256(
    b"DGpy Hook Journal v1\n" +
    json.dumps(
        [sequence, transaction_id, event_type, payload_sha256, previous_sha256],
        ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
).hexdigest()
```

The last digest must match the independently verified expected tip exactly.
The event's own digest is excluded from its hash input. No path, Project
name, user name, hostname, Hook content or other private values belong in
these public event fields. The external payload is **not** opened or checked
by this function. Even its hash should be treated as potentially sensitive
metadata; the review result returns only fixed reason codes and an optional
generic terminal state, never the hashes or transaction ID.

Do **not** treat this experimental encoding as a stable wire format or
production log schema. There is no serializer, parser, MAC, digital signature,
anchor store or authentication key; those need separate threat modeling and
reviews before any real journal design is approved.

## Safety and incomplete evidence

- Evidence missing/invalid: `BLOCKED` before event inspection.
- Invalid collection, too many items, sequence/generation mismatch, broken
  previous hash, incorrect event digest, wrong independent tip or incomplete
  transaction: `BLOCKED`.
- Complete internally consistent chain with an externally *asserted* tip:
  `PREVIEW_ONLY`, **never** `AUTHORIZED`, `SAFE_TO_UNLINK`, or `RESTORED`.
- No filesystem calls, network calls, PII-containing output, or changes to
  other DGpy modules are needed for this consistency calculation.
- The chain **cannot** detect rewriting if an attacker can also rewrite the
  so-called independent trusted tip. Independent authenticated provenance
  is a separate precondition, not achieved here.

Testing uses disposable in-memory examples alongside existing
`tests/test_deployment_preflight.py` and
`tests/test_deployment_lifecycle.py`. This does **not** validate a real
Flame 2026.2.3 session, an actual private transaction journal, or the
product's profile/hook restore behavior.

Related: [2026 Hook Lifecycle Design](2026_HOOK_LIFECYCLE_DESIGN.md).
Production Hook placement, symlink changes, chmod/chown, Flame Setup
Profile Reset/Import and merge remain **NO-GO** pending independent G3/G4
validation and explicit authorization.
