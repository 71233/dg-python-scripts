# Flame 2026.2.3 — key custody and interrupted-recovery preview (NO APPLY)

## Experimental v2 verifier does not relax v1 custody

A [separate generation-bound v2 HMAC preview](2026_HOOK_ANCHOR_V2_PREVIEW.md)
now accepts explicitly *expected* positive generation values after
binding them cryptographically. That v2 entry point is **not called by
this module** and makes no automatic v1-to-v2 migration. This v1
`assess_recovery_preview()` remains restricted to **generation 1**.
Key generation, rotation, revocation, independent anti-replay checkpoint
and operational recovery still need separate independently verified
authorities and isolated Flame tests.

**Status: experimental, isolated-test-only, read-only.** The
`deployment/custody_review.py` module adds
`assess_recovery_preview()` to put a **key lifecycle and independently
reviewed revision gate** in front of the existing HMAC anchor and journal
checks. It does not read or store key material, generate a signing key,
revoke/rotate keys, authenticate a custody service, open a Hook, or change
files, profiles, or Flame state. **Never run production installation or
restoration from a `PREVIEW_ONLY` result.**

## Why the extra gate is necessary

[HMAC anchor review](2026_HOOK_HMAC_ANCHOR_REVIEW.md) confirms a MAC
against *the key supplied to the verifier*. Without additional,
independently protected evidence it cannot know whether that key has
been revoked, retired, rotated, substituted, or whether a newer journal
revision supersedes the anchor. The added wrapper is deliberately
conservative:

| Externally attested condition | Preview outcome |
| --- | --- |
| Any trust or isolation attestation missing | `BLOCKED` **before looking at custody/anchor/key/events** |
| Key state `REVOKED` or `RETIRED` | `BLOCKED` before HMAC; no automatic reactivation |
| Unknown key state, identity, scope, version or transaction | `BLOCKED` |
| Key generation not exactly **1** | `BLOCKED`; rotation requires a separately reviewed **new authenticated protocol** |
| Custody's current revision differs from separately attested revision | `BLOCKED` before HMAC |
| Supplied anchor is older than independently attested revision | HMAC verifier returns `BLOCKED` |
| Incomplete, truncated, reordered or forged journal events | `BLOCKED`; **manual reconciliation**, never automatic retry |
| All model checks appear consistent | `PREVIEW_ONLY` and `NO_CHANGE`, **not operational approval** |

## Pure in-memory contract

The frozen `KeyCustodySnapshot` contains only generic metadata:
`DGpy-Key-Custody-v1` protocol, exact Flame `2026.2.3` version,
`user` or `shared` scope, transaction ID, key ID, key generation,
key lifecycle state, and the purported current revision. There are
**no keys, paths, project names, credentials or file contents** in the
snapshot or public findings.

`CustodyReviewEvidence` explicitly requires *independently established*
operator attestations: custody origin, current revocation status,
current protected revision, anchor origin and **disposable environment**.
The independently expected key ID, transaction ID, scope, generation
and revision are checked against the snapshot before passing their
values to `assess_hmac_journal_preview()`.

These `True` flags are **claims supplied by a caller**, not proof.
No trustworthy snapshot retrieval, protected monotonic counter,
revocation-list verifier, signature, keychain/HSM integration, key
rotation/revocation service or ACL/mount proof is implemented.
An attacker able to replace the independent evidence and key can make
a fabricated chain look internally consistent.

### V1 rotation limitation

The existing HMAC anchor's signed fields **do not include a key
generation**. Therefore the prototype accepts **generation 1 only**,
and requires independently enforced **non-reuse of key IDs**. Key
generation 2 or later always stops with
`key_rotation_requires_new_protocol`; it is **not** a key rotation
mechanism. Historical verification with retired keys is not
implemented either. A production-capable future protocol would need a
versioned authenticated generation, explicit signer/key custody,
revocation and replay protection. Do not add a silent compatibility
fallback that bypasses this check.

### Interrupted transactions

The current v1 HMAC anchor model only supports **completed** event
chains: `ACTIVE` (three events) and `DISABLED` (five events).
Intermediate `INTENT`, `LINK_CREATED`, and `DISABLE_INTENT` histories
cannot be certified by this model. Event-count and integrity mismatches
return `BLOCKED`. The `RecoveryPreview.next_step` is
`MANUAL_RECONCILIATION` for **every** blocked result.

That is a **request for manual investigation**, not permission for a
person or automated script to delete a link, reset Flame, replay an
intent, roll back settings, or infer which filesystem state is real.
Even `PREVIEW_ONLY` yields `NO_CHANGE`: no operation should follow.
The code does **not** claim to establish what Flame has loaded or
whether a prior symlink was installed/removed.

## Validation and testing

- `tests/test_deployment_custody.py`: **44** isolated tests with the
  underlying HMAC reviewer mocked. These verify that invalid or
  untrusted custody metadata never reaches the reviewer, including
  revoked/retired/rotated keys, stale revisions, malicious subclassed
  inputs, unknown scopes and non-actionable results.
- `tests/test_deployment_custody_integration.py`: **9** deterministic
  in-memory integration tests, exercising the **actual** HMAC reviewer
  and SHA-256 journal chain, including an interrupted journal, old
  authenticated revision, a revoked key, tampered events, and the
  separately bound Shared scope. Fixture key bytes are **public test
  values**, not a production secret.
- The 44 mocked tests passed in a disposable Python **3.13.5**
  container. New source and both test files parsed using Python 3.11
  grammar. The nine HMAC/journal integration tests and all Public tests
  passed in [GitHub Actions run 45168207871](https://github.com/71233/dg-python-scripts/actions/runs/45168207871):
  **267/267** on Ubuntu 24.04 / Python **3.11**, including editable
  package installation and successful wheel build.
  This is not Flame's exact Python 3.11.5 on macOS.

This scope is deliberately separate from existing
[Hook preflight](2026_HOOK_PREFLIGHT.md),
[journal chain](2026_HOOK_JOURNAL_REVIEW.md),
[HMAC anchor](2026_HOOK_HMAC_ANCHOR_REVIEW.md) and
[NO-APPLY lifecycle design](2026_HOOK_LIFECYCLE_DESIGN.md).

## Operational gates

Only a **production Mac** is available to the user. A separate
disposable Flame 2026.2.3 instance and its effective Hook root
isolation have not been established. No tests have been performed
against the actual Flame-bundled Python **3.11.5** or a real Hook.

**G3/G4 remain NO-GO**: do not change existing Hook directories
or `0777` permissions, symlink files, reinstall/reset Flame, run
Setup Profile Export/Import as a recovery experiment, or merge/deploy
this prototype. Keep the Public and Internal PRs Draft until isolated
real-machine testing and explicit authorization become possible.
