# DGpy machine setup (macOS / Linux)

This is a repeatable **user-scoped** installer for checkout-based development of
Flame 2025.2.7 scripts. It uses the existing
[`chore/dev-workflow`](https://github.com/71233/dg-python-scripts/pull/4)
helper, so it is not a replacement for `dgpy-update`, `dgpy-setup`, or
`dgpy-flame`. Until PR #4 is merged, use its branch.

## Ownership and layout

- Source: `~/DGpy/dg-python-scripts` and optionally `~/DGpy/dg-python-scripts-internal`.
- Versioned helper copies: `~/DGpy/.dgpy-tool-versions/<public-commit>`.
- Stable command symlink: `~/DGpy/bin-managed` (points to one versioned copy).
- User config: `~/DGpy/site.toml`, created only if Internal is requested and the file is absent.
- **Only one Flame hook**: `dgpy_bootstrap.py` links back to the Public checkout.
  - Linux: `~/flame/python/dgpy_bootstrap.py`
  - macOS: `~/Library/Preferences/Autodesk/flame/python/dgpy_bootstrap.py`

Flame's standard Python hook paths are OS-user-specific. On a studio Linux
machine where `~/flame` is swapped while changing Flame User, **load the
intended Flame User first**, then run setup. The installer never changes
Flame User, `HOME`, `~/flame`, or existing search-path configuration.

## Start on a new computer

Prerequisites: Git, network access to GitHub, and an authorized Flame
2025.2.7/Python 3.11.5 installation. GitHub credentials/access must already
be configured if Internal is needed. No sudo or system-wide `pip install`
is required. From a *trusted copy* of the Public script:

```sh
# First download the script, then inspect before running.
curl -fsSLo dgpy-machine.sh \
  https://raw.githubusercontent.com/71233/dg-python-scripts/chore/dev-workflow/tools/dgpy-machine.sh
sh dgpy-machine.sh --with-internal
sh dgpy-machine.sh --with-internal --apply
```

Omit `--with-internal` for Public-only first install, or use
`--public-only` explicitly. Omitted Internal option retains an already
existing Internal checkout but does not clone one on a new computer.

The first invocation is **preview-only**. The second clones or updates the
requested checkouts, creates the missing current-user bootstrap symlink,
checks hooks with `dgpy-status`, installs versioned commands, and points
`bin-managed` at the resulting version. It does not launch Flame.

Re-run the same `sh dgpy-machine.sh ... --apply` command to refresh
existing branches safely (fast-forward only). It never silently switches
an already checked-out branch, overwrites an existing foreign hook, or
resets dirty source. Use explicit checkout branch options only when
**cloning**. Use the existing `dgpy-switch` helper for a deliberate branch
change after verifying the correct target.

Inspect the result with:

```sh
"$HOME/DGpy/bin-managed/dgpy-status" --root "$HOME/DGpy" --repo all
"$HOME/DGpy/bin-managed/dgpy-flame" --root "$HOME/DGpy" --dry-run
```

For Public-only use `--repo public` for status. To start Flame with Internal:

```sh
"$HOME/DGpy/bin-managed/dgpy-flame" --root "$HOME/DGpy" \
  --with-internal --config "$HOME/DGpy/site.toml" --dry-run
# After reviewing the plan and stopping the existing Flame process:
"$HOME/DGpy/bin-managed/dgpy-flame" --root "$HOME/DGpy" \
  --with-internal --config "$HOME/DGpy/site.toml"
```

Environment variables for the DGpy package only apply to this Flame
launch session. Launching Flame normally from the system does not
inherit them. After any checkout/config change, quit and restart Flame.

## Existing studio/shared checkouts (recommended on shared Linux)

Do **not** let every workstation fetch or modify a shared source directory.
Use the `--shared` mode, which requires an already existing clean checkout
and **never runs clone/fetch/merge/switch**:

```sh
sh dgpy-machine.sh --shared --with-internal \
  --root "/path/to/managed/DGpy" --state-dir "$HOME/DGpy" \
  --check-hook-dir "/path/to/known/shared/hooks"
sh dgpy-machine.sh --shared --with-internal --apply \
  --root "/path/to/managed/DGpy" --state-dir "$HOME/DGpy" \
  --check-hook-dir "/path/to/known/shared/hooks"
```

Here `/path/to/managed/DGpy` is an **example placeholder**, not a site
configuration. Specify actual known shared, project, and versioned hook
roots using repeated `--check-hook-dir`; the tool cannot discover every
Flame hook search root. Do not modify common old DGpy copies or hooks.
The script only creates the current-user symlink and copies tools to
`--state-dir`. Pass `--root "/path/to/managed/DGpy"` when invoking the
installed `dgpy-flame` or `dgpy-status` commands.

Update shared source only during a coordinated downtime, using the existing
`dgpy-update` workflow from the one designated maintenance machine;
users re-run `--shared --apply` after it is updated.

## Safety and limitations

- No `sudo`, no shell profile edits, no uninstall/migration of old hooks,
  no automatic Flame User switching, and no deletion of user configuration.
- Existing checkouts must be clean; only tracked upstream fast-forward is
  permitted. If a conflict or unavailable GitHub access occurs, stop and
  inspect without force reset, stash, or automatic credential changes.
- The script checks explicitly supplied hook roots and the existing
  `DL_PYTHON_HOOK_PATH`. Alias-named ordinary copies, hidden Flame-specific
  roots, or menu duplicates need an operator check before launch.
- An external edit during update is not preventable by the per-user lock;
  shared code must be updated while nobody is running Flame from it.
- A failed first install might leave a new clone or an already-created hook;
  rerun after resolving the issue. Previous non-owned files are preserved.
- Versioned helper copies are retained for safety; cleanup/rollback is
  manual and is **not** part of this installer.
- Mac and Linux real Flame GUI installation/launch remains a separate host
  validation. The automated test uses disposable Git origins and hook paths.
- Run `sh dgpy-machine.sh --help` to see all options.

## Validation record

Initial implementation: Public PR #4, `tools/dgpy-machine.sh` and
`tests/test_machine_setup.py`. Local isolated shell-fixture run covered
preview, first install, re-run, fast-forward, dirty-tree refusal,
shared attach without update, and config preservation. It did not
connect to real GitHub or launch Autodesk Flame. CI for the final PR
commit and Mac/Linux host testing must be checked separately.

See [DEV_WORKFLOW.md](DEV_WORKFLOW.md) for existing command contracts and
[FLAME_NOTES.md](FLAME_NOTES.md) for host observations.
