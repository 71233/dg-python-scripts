# Flame 2026.2.3 Hook deployment preflight (experimental)

This is a **read-only, fail-closed assessment** for planning DGpy's single
`dgpy_bootstrap.py` placement. It is **not an installer**, repair utility,
or authorization to touch production Flame Hook directories. The first
implementation does not include a CLI or an `apply` action.

The shared module lives in `src/dg_python_scripts/deployment/preflight.py`.
It imports no Flame, Qt, or PySide modules. The public DGpy bootstrap remains
the sole proposed DGpy entry point in Flame's Hook search paths. The 2025.2.7
setup scripts in Public draft PR #4 are **not** used or modified by this work.

## Documented search scopes and limitations

The Autodesk Flame 2026 Hook Reference documents User, Project, Application,
Shared, and optional `DL_PYTHON_HOOK_PATH` directories:

- https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Flame_API_Python_Hooks_Reference_html.html
- https://help.autodesk.com/cloudhelp/2026/ENU/FLAME-install-software-config/files/centralised_components.html

`assess_bootstrap()` takes an **explicit list** of `HookRoot` objects. It
does not guess the active Project, infer User HOME, parse sysconfig on its
own, or automatically enumerate the effective Hook roots. This prevents a
successful-looking result caused by an incomplete directory search.

An operator must provide exactly one root for each standard scope (User,
Project, Application, Shared) and a separate `scope="extra"` entry for each
confirmed additional Hook directory. `path=None` means unknown, not absent.
A known directory that does not exist is distinct from an unknown root.
A **non-target** User directory (possibly not created before first launch)
or Project directory may be absent. A missing target **User or Shared**,
Application, non-target Shared, or explicitly supplied extra directory
BLOCKS the assessment. The function never creates any directory.

The `Evidence` flags are explicit **operator attestations**. By default all
are unknown and the assessment is BLOCKED. They include a confirmed exact
Flame version (`2026.2.3` for this initial prototype), complete known standard
roots, the verified completeness of additional path entries, independent
ownership/ACL/mount review, and source checkout/revision provenance. Setting
any flag to True without real evidence invalidates the assessment.

## Static checks

- Reject missing/duplicate standard scopes, unknown extra search roots,
  relative paths, path traversal, wrong target scope, or wrong Flame version.
- Reject source missing, wrong filename, non-regular source, a symlink in the
  source or its ancestors, world-writable source, or source within a Hook root.
- Reject a missing target or unexpected missing non-target Hook directory,
  non-directory roots, a symlink in any supplied root path, unreadable roots,
  duplicate root paths/inodes, **or overlapping ancestor/descendant roots**.
- Reject **any world-writable inspected Hook root**, including one not used
  as the target. The observed 0777 User/Shared roots in the 2026.2.3
  environment will therefore BLOCK the plan; no `chmod` workaround is made.
- Reject any `dgpy*`/`dg_python_scripts*` direct entry, including dangling
  symlinks; existing files are **never overwritten**, even if a symlink might
  point to the same source.
- Reject direct `.py` symlinks, duplicate case-folded `.py` basenames among
  supplied roots, **direct hard links to the selected Bootstrap source**,
  and entry/root changes that make an in-progress scan inconsistent.
  Filename folding is conservative on potentially case-insensitive macOS
  filesystems; it does not claim Flame's loader is case-insensitive.

Findings contain only stable issue codes and standard scope identifiers, **no
hostnames, Project names, actual filenames, file contents, or private paths**.
`report.status` is either `BLOCKED` or `PREVIEW_ONLY`.
**`PREVIEW_ONLY` does not mean safe to install**: it merely means this limited
static scanner did not find a blocker with the supplied and attested inputs.

## Deliberate exclusions

This version does **not** verify real Hook loading, arbitrary alternate
filenames or dynamic imports, recursive subdirectories, content-identical
copies with different inodes, hidden hard-link aliases outside supplied
direct `.py` entries, actual Flame import paths, per-Project behavior
beyond one explicitly supplied
Project root, all system users, menu/UI registration, or the root priority
order. It does not determine whether a machine's storage is physically local,
or validate ACLs, network mounts, user ownership, and symlink races in depth.
The corresponding `Evidence.security_reviewed=True` remains an **external
review**, not a platform security guarantee. The check is not atomic;
filesystem contents may change before any eventual installation.

Directory scans are non-mutating but can trigger filesystem access-time
changes or remote automount activity. They must be run only on authorized
paths and stopped if a shared mount is unresponsive.

## Testing and project gates

Run in a disposable checkout/fixture environment, not by installing in Flame:

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_deployment_preflight.py' -v
```

The initial 29 disposable-directory tests were extended with nine regression
tests covering non-target missing directories, overlapping Hook roots,
hard-linked Bootstrap aliases, disappearing directories and failed entry
stat checks. All **38 isolated fixture tests** passed on Python 3.13.5,
and the changed code and tests parsed under Python 3.11 grammar.

Before this review, GitHub Actions
[CI run 45154894764](https://github.com/71233/dg-python-scripts/actions/runs/45154894764)
passed the **75-case Public suite** and wheel build on Ubuntu 24.04 /
Python 3.11. The updated **38-test** preflight code needs a fresh CI
confirmation on this PR head; earlier CI does not verify these changes.
Neither result verifies the exact Flame-shipped Python 3.11.5 runtime on
macOS or actual Flame Hook imports or menu behavior.
Do not present these unit tests as Flame 2026 integration testing.

See also [single-Bootstrap installation, disable and recovery design
(NO APPLY)](2026_HOOK_LIFECYCLE_DESIGN.md). No state-changing operations
have been implemented.

Next stages, each requiring separate evidence:

1. Review correctness and compatibility with the Public existing tests/CI,
   including actual Python 3.11.5 execution, and collect review feedback.
2. Add only a separately reviewed preview of source/target and rollback
   actions. Do **not** add an `apply` path until safe failure/rollback and
   ownership/mount proof are accepted.
3. Validate one isolated/disposable Flame 2026.2.3 User/Project and a single
   Bootstrap, its UI appearance, restart/reload behavior, context selection,
   duplicate avoidance, and restoration.
4. Only after isolated success and explicit authorization, consider
   production deployment. Production Hook writes and Profile Reset/Import
   remain **NO-GO** in this development stage.
