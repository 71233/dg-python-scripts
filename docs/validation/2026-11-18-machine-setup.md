# 2026-11-18 per-machine DGpy install/refresh implementation

## Scope and source

Reuse Public [Draft PR #4](https://github.com/71233/dg-python-scripts/pull/4)
on `chore/dev-workflow`. Existing `tools/dgpy`, `tools/dgpy_dev.py`,
`dgpy-setup`, `dgpy-update`, and `dgpy-flame` are retained.
The change introduces `tools/dgpy-machine.sh` plus
`tests/test_machine_setup.py`, documentation in
[MACHINE_SETUP](../MACHINE_SETUP.md), and documentation links.
No Internal production code, real Flame Hook, Flame User, or existing
command installation was modified while developing this change.

Initial Github head at inspection: Public `195ef47f217638a5bb5651a017369fa4037d2c45`,
Internal `a616d122112361f3e850cae1b2022bfb0be37da7`.
Both feature PRs were open/draft, unmerged. GitHub does not expose each
operator machine's local working tree state, so no clean local checkout
was assumed.

## Intended behavior

- No `--apply`: print the intended checkout, command path and user Hook.
- Public new machine: clone branch `chore/dev-workflow` (until PR #4 merges);
  for already existing clean checkouts preserve their branch and delegate
  fast-forward-only updates to `dgpy-update`.
- `--with-internal`: clone/access Internal only when explicitly requested.
  Never add private site details to Public.
- `--shared`: require existing clean checkouts and **do not clone, fetch,
  merge, switch or modify Git**. Only link the current user's Hook and
  prepare local commands/config.
- Install only the single `dgpy_bootstrap.py` symlink into the explicit
  or OS-default user Hook dir; refuse conflicts, foreign links and
  duplicate candidates found by the shared helper.
- Keep versioned command copies under the user's state directory;
  update the managed pointer only after a successful helper install.
  Existing command directory/symlink owners are protected.
- Do not write shell startup files, change HOME, switch Flame User,
  touch old Hook installations, or launch Flame during installation.
- GitHub private access is a prerequisite for Internal; no authentication
  changes are made automatically.

## Executed tests and limits

1. `sh -n` passed for the shell script in the isolated execution container.
2. A disposable POSIX shell test fixture using local bare Git remotes and
   fake `dgpy` command implementations passed: preview with no changes,
   first clone and setup, repeatability, a fast-forward, `--shared` with no
   Git HEAD mutation, refusal of a dirty tree, preservation of an edited
   TOML site config. These are **mock helper** integration checks.
3. Added a repository-level unittest `tests/test_machine_setup.py`,
   which uses real `tools/dgpy` and `tools/dgpy_dev.py` copied into
   temporary local Git origins. GitHub Actions verifies these tests for
   the published version; final CI must be read from the PR checks.
4. Flame 2025.2.7 GUI and actual Linux/macOS user Hook directories were
   **not** changed or measured during this task. Host verification
   remains required, especially hook duplicate detection, source
   `module.__file__`, existing legacy hooks and branch/restart reload.

## Remaining checks

- Verify latest PR #4 CI Linux/macOS suite, wheel, and Python 3.6/3.11
  entrypoint jobs after final documentation updates.
- Perform real Mac and Linux smoke tests with a disposable Flame User /
  explicitly approved user Hook, verifying preview then apply.
- Test existing user Hook conflicts, optional Internal authentication,
  shared source with separate user-local state, and Flame launch using
  the explicit `--root` option.
- Check `dgpy-status` plus a single menu registration and
  `dg_python_scripts.__file__` after starting Flame via `dgpy-flame`.
  Record both repos' branch, full commit, tree/dirty, OS and Flame build.
- Keep PR #4 Draft until the host checks are recorded. Internal PR #1
  still owns the existing Internal launcher/CI documentation. No merge.

