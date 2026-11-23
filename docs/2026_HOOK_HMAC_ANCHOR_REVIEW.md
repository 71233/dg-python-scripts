# Flame 2026.2.3 — keyed journal anchor preview (NO APPLY)

**Status: experimental, isolated-test-only verification.** The new
`deployment/anchor_review.py` is a **pure, read-only** HMAC-SHA256 verifier for
an externally supplied anchor plus an in-memory journal event list. It neither
creates nor persists a key, anchor, journal, Hook, signature, or MAC. It never
imports Flame/Qt, reads Hook directories, calls Flame APIs, changes profiles,
or executes any file operation. It has **no install, unlink, disable, restore,
signing, key-management, or `apply` entry point**.

Public API: `JournalAnchor`, `AnchorReviewEvidence`, and
`assess_hmac_journal_preview()` in `dg_python_scripts.deployment`.

## What the MAC establishes — and does not

An HMAC-SHA256 match establishes that the anchor bytes correspond to the
**specific secret key supplied for that check**. It does **not** establish
whether that key belongs to the approved operator, whether the key was
compromised, whether the anchored events reflect real Flame operations,
or whether the anchor is current. A holder of a compromised key can
recompute the MAC and fabricate matching events.

The function requires *external, independently established* attestations:

- `key_origin_confirmed=True`: a trusted process reviewed key provenance and
  confidentiality independently of the untrusted journal;
- `anchor_origin_confirmed=True`: the anchor and expected identity came from an
  approved, independent source rather than the same editable journal;
- `isolated_environment_confirmed=True`: this is a disposable environment,
  **not** the user's only production Mac;
- an independent expected `key_id`, `transaction_id`, `scope` (`user` or
  `shared`) and `revision` (1 = `ACTIVE`, 2 = `DISABLED`).

The code cannot itself verify these external attestations. Any unknown
attestation or malformed expected field returns `BLOCKED` **before inspecting
anchor/key/events**. Callers must **never** create a key from journal contents
or treat strings such as `"yes"` as a valid attestation.

The in-memory `trusted_key` must be an exact `bytes` object of **32–64 bytes**.
**No actual secret key, environment variable, credential, key file path, or
production journal belongs in GitHub, tests, comments, logs, or this chat.**
The included tests use a deterministic *public* 32-byte fixture — it is not
an operational secret. An authentic key manager, lifecycle, rotation,
revocation and monotonic revision service have **not** been built or tested.

## Fixed v1 anchor format and authenticated bytes

A frozen `JournalAnchor` carries **no key**. Its fields are:

| Field | Requirement |
| --- | --- |
| `protocol` | Exact literal `DGpy-Hook-Anchor-v1` |
| `flame_version` | Exact `2026.2.3` (current prototype gate) |
| `scope` | `user` or `shared`, bound to an independently expected scope |
| `key_id` | ASCII identifier (1–64 chars), independently matched |
| `transaction_id` | ASCII identifier (1–64 chars), independently matched |
| `revision` | `1` for `ACTIVE` or `2` for `DISABLED` |
| `event_count` | `3` for `ACTIVE` or `5` for `DISABLED` |
| `terminal_state` | `ACTIVE` or `DISABLED` |
| `tip_sha256` | 64 lowercase hexadecimal characters |
| `mac_sha256` | HMAC-SHA256, 64 lowercase hexadecimal characters |

The MAC covers a *versioned, domain-separated, canonical* serialization of
all preceding fields, excluding `mac_sha256`:

```python
message = json.dumps(
    [protocol, flame_version, scope, key_id, transaction_id,
     revision, event_count, terminal_state, tip_sha256],
    ensure_ascii=True, separators=(",", ":"),
).encode("ascii")
expected_mac = hmac.new(
    trusted_key,
    b"DGpy Hook Anchor HMAC-SHA256 v1
" + message,
    hashlib.sha256,
).hexdigest()
```

The verifier compares lowercase digest strings with `hmac.compare_digest`.
This is an **experimental format, not a stable signed-file schema or
approved production protocol**. Canonical encoding is precisely specified so
the disposal-only fixtures can be independently reproduced; this document is
**not** an instruction to generate, save, or sign a production anchor.

## Safe validation order

1. Verify exact input classes and independent attestations. Reject unknown
   scope, key ID, transaction ID, revision or invalid key length/type.
2. Validate all anchor metadata and match the independently supplied
   expected identity and revision (including known `ACTIVE`/`DISABLED`
   event counts). A signed older revision must be rejected.
3. Compare the HMAC. If it fails, **do not inspect the event list**.
4. Only then inspect the bounded event list using the existing
   `assess_journal_preview()`: event ordering, zero-based sequence, same
   transaction ID, event SHA-256 chain, anchored tip and terminal state.
5. Return sanitized `BLOCKED` reasons on any mismatch, or `PREVIEW_ONLY` if
   this model matches. **Neither status grants a state-changing action.**

The function never returns the key, MAC, transaction ID, journal payloads,
file path, private project name or source content. It never emits exceptions
containing a private path as part of its structured result.

## Residual risks and explicit NO-GO conditions

- `expected_revision` is supplied, **not protected by a real monotonic
  external counter**. Replaying an old, validly signed anchor is undetectable
  if a caller accepts the same stale revision. A separate authenticated
  revision source and key/anchor custody design are prerequisites.
- HMAC does not assert that `ACTIVE` means Flame actually loaded a Hook or
  that `DISABLED` means a managed link has been safely removed.
- The journal chain contains hashes of *external private evidence*. The
  verifier does not open or authenticate that evidence, validate ACL/mount
  safety, prove journal durability, or establish installer ownership.
- An attacker controlling both the key and independent anchor source can
  forge a consistent journal; a **test explicitly documents this boundary**.
- No real key generation, encrypted storage, key rotation/revocation,
  signer/HSM, anchor storage, file parser/writer, crash recovery, atomic
  transaction or approved replay protection exists.
- The user's only Flame 2026.2.3 Mac is a **production Mac**, not a
  disposable environment. Production Hook creation/removal, symlink changes,
  chmod/chown, Flame Setup Profile Reset/Import and merging the Draft PRs
  remain **NO-GO**.

## Test evidence

The new `tests/test_deployment_anchor.py` includes **45** in-memory
fixture tests: valid active/disabled snapshots, wrong/missing HMAC keys,
MAC/tip substitution, stale revisions, metadata substitution, hostile input
classes, event-count changes, journal tampering, redacted results, and
absence of filesystem operations. The adjacent 38 preflight, 42 managed-link
and 43 chain tests bring the isolated Python 3.13.5 total to **168**.
Python 3.11 grammar parsing succeeded for the new code and tests.

These are **unit tests only**. Verify the **current PR head's** GitHub
Actions full Python 3.11 suite before recording the new CI result.
Nothing here verifies the exact Flame-bundled Python 3.11.5 on macOS,
actual Hook loading, UI, Selection, or recovery.

See [journal chain review](2026_HOOK_JOURNAL_REVIEW.md),
[single-Bootstrap lifecycle design](2026_HOOK_LIFECYCLE_DESIGN.md), and
[preflight](2026_HOOK_PREFLIGHT.md).
