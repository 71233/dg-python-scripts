#!/usr/bin/env python3
"""DGpy development checkout helpers (stdlib only, Python 3.9+)."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys


class Unsafe(RuntimeError):
    pass


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise Unsafe(f"{repo}: git {' '.join(args)}\n{result.stderr.strip()}")
    return (result.stdout if "-z" in args else result.stdout.strip()) if check else result


def repositories(args):
    root = args.root.expanduser().resolve()
    names = {"public": "dg-python-scripts", "internal": "dg-python-scripts-internal"}
    keys = names if args.repo == "all" else [args.repo]
    repos = [(key, root / names[key]) for key in keys]
    for key, repo in repos:
        if not repo.is_dir() or Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
            raise Unsafe(f"{key}: expected a repository root at {repo}")
    return repos


def clean(repo):
    if git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise Unsafe(f"{repo}: dirty tree (including untracked files); commit or move changes first")
    for state in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer", "BISECT_LOG", "index.lock"):
        path = Path(git(repo, "rev-parse", "--git-path", state))
        if not path.is_absolute():
            path = repo / path
        if path.exists():
            raise Unsafe(f"{repo}: Git operation/lock present: {state}")
    if not git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).returncode == 0:
        raise Unsafe(f"{repo}: detached HEAD; select a branch manually first")


def ref_exists(repo, ref):
    return git(repo, "show-ref", "--verify", "--quiet", ref, check=False).returncode == 0


def ancestor(repo, old, new):
    return git(repo, "merge-base", "--is-ancestor", old, new, check=False).returncode == 0


def tracking(repo, branch):
    remote = git(repo, "config", "--get", f"branch.{branch}.remote", check=False).stdout.strip()
    merge = git(repo, "config", "--get", f"branch.{branch}.merge", check=False).stdout.strip()
    if remote != "origin" or not merge.startswith("refs/heads/"):
        raise Unsafe(f"{repo}: {branch} must track an origin branch")
    return "refs/remotes/origin/" + merge[len("refs/heads/"):]


def synchronize(args):
    repos = repositories(args)
    # Preflight every checkout before fetching or changing any working tree.
    for _, repo in repos:
        clean(repo)
    if args.command == "switch":
        branch = args.branch
        if branch.startswith("-") or branch == "HEAD" or "@{" in branch:
            raise Unsafe("An explicit branch name is required")
        for _, repo in repos:
            git(repo, "check-ref-format", "--branch", branch)
    plans = []
    for key, repo in repos:
        git(repo, "fetch", "--prune", "origin")
        if args.command == "switch":
            branch = args.branch
            target = "refs/remotes/origin/" + branch
            local = "refs/heads/" + branch
            exists = ref_exists(repo, local)
            if exists and tracking(repo, branch) != target:
                raise Unsafe(f"{repo}: existing {branch} tracks a different branch")
        else:
            branch = git(repo, "symbolic-ref", "--short", "HEAD")
            target = tracking(repo, branch)
            local, exists = "HEAD", True
        if not ref_exists(repo, target):
            raise Unsafe(f"{repo}: origin branch missing: {target}")
        if exists and not ancestor(repo, local, target):
            raise Unsafe(f"{repo}: local branch is ahead or diverged; refusing to change it")
        # An ignored file must never be overwritten by a branch change.
        ignored = git(repo, "ls-files", "--others", "--ignored", "--exclude-standard", "-z").split("\0")
        tracked = git(repo, "ls-tree", "-r", "--name-only", "-z", target).split("\0")
        if any(a and b and (a == b or a.startswith(b + "/") or b.startswith(a + "/"))
               for a in ignored for b in tracked):
            raise Unsafe(f"{repo}: ignored files overlap target branch; move them first")
        plans.append((key, repo, branch, target, exists, git(repo, "rev-parse", "HEAD"),
                      git(repo, "symbolic-ref", "HEAD"), git(repo, "rev-parse", target),
                      git(repo, "rev-parse", local) if exists else None))
    # Check every checkout again before mutating the first one. Pin fetched
    # commits so an external fetch cannot silently change the update target.
    for key, repo, branch, target, exists, head, current, commit, local_head in plans:
        clean(repo)
        local = "refs/heads/" + branch
        if (git(repo, "rev-parse", "HEAD") != head
                or git(repo, "symbolic-ref", "HEAD") != current
                or ref_exists(repo, local) != exists
                or (exists and git(repo, "rev-parse", local) != local_head)
                or git(repo, "rev-parse", target) != commit
                or (exists and tracking(repo, branch) != target)):
            raise Unsafe(f"{repo}: branch/ref changed during preflight")
    for key, repo, branch, target, exists, head, current, commit, local_head in plans:
        clean(repo)
        if git(repo, "rev-parse", "HEAD") != head or git(repo, "symbolic-ref", "HEAD") != current:
            raise Unsafe(f"{repo}: HEAD/branch changed before update")
        if args.command == "switch":
            if exists:
                git(repo, "checkout", "--no-overwrite-ignore", branch)
            else:
                git(repo, "checkout", "--no-overwrite-ignore", "-b", branch, commit)
                git(repo, "branch", "--set-upstream-to=" + target, branch)
        git(repo, "merge", "--ff-only", commit)
        print(f"Updated {key}: {repo}\n  branch: {branch}\n  commit: {git(repo, 'rev-parse', 'HEAD')}\n  tree: {'dirty' if git(repo, 'status', '--porcelain', '--untracked-files=all') else 'clean'}")
    print("Restart Flame to reliably reload package code. Multiple repos are not an atomic transaction.")


def hook_dir(args):
    if args.hook_dir:
        return args.hook_dir.expanduser().absolute()
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Preferences/Autodesk/flame/python"
    if system == "Linux":
        return Path.home() / "flame/python"
    raise Unsafe("Use --hook-dir on this platform")


def link_state(destination, source):
    if destination.is_symlink():
        return "OK" if destination.resolve() == source.resolve() and source.is_file() else "CONFLICT/BROKEN"
    return "CONFLICT" if os.path.lexists(destination) else "MISSING"


def links(args):
    root = args.root.expanduser().resolve()
    sources = [root / "dg-python-scripts/bootstrap/dgpy_bootstrap.py"]
    for value in args.probe:
        source = Path(value).expanduser().resolve()
        internal = root / "dg-python-scripts-internal"
        if internal not in source.parents or source.suffix != ".py":
            raise Unsafe("Probes must be explicit .py files inside the internal checkout")
        sources.append(source)
    if len({source.name for source in sources}) != len(sources):
        raise Unsafe("Duplicate hook filenames in the requested setup")
    return [(hook_dir(args) / source.name, source) for source in sources]


def duplicate_hooks(args, plan):
    """Conservative scan of explicitly known hook roots; never modifies hooks."""
    roots = [hook_dir(args), *args.check_hook_dir]
    roots.extend(Path(value).expanduser() for value in
                 os.environ.get("DL_PYTHON_HOOK_PATH", "").split(os.pathsep) if value)
    destinations = {source.resolve() for _, source in plan}
    intended = {destination.absolute() for destination, _ in plan}
    names = {source.name for _, source in plan}
    found = set()
    for root in roots:
        root = root.expanduser().absolute()
        if not root.exists():
            continue
        if not root.is_dir():
            raise Unsafe(f"Hook search root is not a directory: {root}")
        for path in root.rglob("*.py"):
            # Exact destinations are expected. Alternate root aliases for them
            # are conservative conflicts because Flame may search both roots.
            if path.absolute() in intended:
                continue
            if path.name in names or (path.is_symlink() and path.resolve() in destinations):
                found.add(path)
    return sorted(found)


def status(args):
    failed = False
    for key, repo in repositories(args):
        branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        changes = git(repo, "status", "--porcelain", "--untracked-files=all")
        upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
        print(f"{key}: {repo}\n  branch: {branch.stdout.strip() or '(detached)'}\n  commit: {git(repo, 'rev-parse', 'HEAD')}\n  tree: {'dirty' if changes else 'clean'}\n  upstream: {upstream.stdout.strip() or '(none)'}")
        if upstream.returncode == 0:
            print("  ahead/behind (last fetch): " + git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"))
        if changes:
            print(changes)
    for destination, source in links(args):
        state = link_state(destination, source)
        print(f"hook: {state}: {destination} -> {source}")
        failed |= state != "OK"
    for path in duplicate_hooks(args, links(args)):
        print(f"hook: DUPLICATE CANDIDATE: {path}")
        failed = True
    # Existing probe links are shown even when no --probe was supplied.
    for path in sorted(hook_dir(args).glob("dgpy*probe*.py")):
        valid = path.is_symlink() and path.exists()
        print(f"probe: {'linked' if valid else 'unmanaged/broken'}: {path}")
        failed |= not valid
    return 1 if failed else 0


def setup(args):
    plan = links(args)
    duplicates = duplicate_hooks(args, plan)
    if duplicates:
        raise Unsafe("Duplicate hook candidates; inspect before setup: " + ", ".join(map(str, duplicates)))
    for destination, source in plan:
        if not source.is_file():
            raise Unsafe(f"Missing hook source: {source}; switch to the intended branch first")
        state = link_state(destination, source)
        if state.startswith("CONFLICT"):
            raise Unsafe(f"Existing placement protected: {destination}. Move it to a backup outside all hook search paths, then retry.")
        print(f"{state}: {destination} -> {source}")
    if not args.apply:
        print("Preview only; use --apply to create missing symlinks.")
        return
    created = []
    try:
        for destination, source in plan:
            if link_state(destination, source) == "OK":
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(source)
            created.append((destination, source))
    except OSError:
        for destination, source in reversed(created):
            if destination.is_symlink() and destination.readlink() == source:
                destination.unlink()
        raise
    print("Symlinks ready. Use env before launching Flame; verify other hook search paths for duplicate hooks.")


def environment(args):
    root = args.root.expanduser().resolve()
    paths = [root / "dg-python-scripts/src"]
    if args.with_internal:
        paths.append(root / "dg-python-scripts-internal/src")
    for path in paths:
        if not path.is_dir() or ":" in str(path):
            raise Unsafe(f"Invalid source path: {path}")
    exports = ["export PYTHONPATH=" + shlex.quote(":".join(map(str, paths))) + '${PYTHONPATH:+:$PYTHONPATH}']
    if args.config:
        path = args.config.expanduser().resolve()
        if not path.is_file():
            raise Unsafe(f"Missing TOML configuration: {path}")
        exports.append("export DGPY_CONFIG=" + shlex.quote(str(path)))
    print("\n".join(exports))


def install(args):
    directory = args.bin_dir.expanduser().absolute()
    source = Path(__file__).resolve()
    destination = directory / "dgpy"
    names = ("dgpy-update", "dgpy-status", "dgpy-switch", "dgpy-setup")
    if os.path.lexists(destination) and (destination.is_symlink() or not destination.is_file() or destination.read_bytes() != source.read_bytes()):
        raise Unsafe(f"Existing tool protected: {destination}; install into a fresh directory")
    for name in names:
        path = directory / name
        if os.path.lexists(path) and not (path.is_symlink() and path.readlink() == Path("dgpy")):
            raise Unsafe(f"Existing command protected: {path}")
    print(f"Install stable tool copy and command links in {directory}")
    if args.apply:
        directory.mkdir(parents=True, exist_ok=True)
        if not os.path.lexists(destination):
            with destination.open("xb") as stream:
                stream.write(source.read_bytes())
            destination.chmod(0o755)
        for name in names:
            path = directory / name
            if not os.path.lexists(path):
                path.symlink_to("dgpy")
    else:
        print("Preview only; use --apply to install.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "update", "switch", "setup", "env", "install"):
        sub = subs.add_parser(name)
        sub.add_argument("--root", type=Path, default=Path(os.environ.get("DGPY_ROOT", "~/DGpy")))
        if name in ("status", "update", "switch"):
            sub.add_argument("--repo", choices=("public", "internal", "all"), default="all", required=name == "switch")
        if name == "switch":
            sub.add_argument("branch")
        if name in ("status", "setup"):
            sub.add_argument("--hook-dir", type=Path)
            sub.add_argument("--check-hook-dir", type=Path, action="append", default=[],
                             help="additional hook search root to scan for duplicates (repeatable)")
            sub.add_argument("--probe", action="append", default=[])
        if name in ("setup", "install"):
            sub.add_argument("--apply", action="store_true")
        if name == "env":
            sub.add_argument("--with-internal", action="store_true")
            sub.add_argument("--config", type=Path)
        if name == "install":
            sub.add_argument("--bin-dir", type=Path, default=Path("~/DGpy/bin"))
    if argv is None:
        argv = sys.argv[1:]
        executable = Path(sys.argv[0]).name
        if executable.startswith("dgpy-"):
            command = executable[len("dgpy-"):]
            # dgpy-setup also offers env and install subcommands.
            argv = argv if command == "setup" and argv[:1] in (["env"], ["install"]) else [command, *argv]
    args = parser.parse_args(argv)
    try:
        if args.command in ("update", "switch"):
            # Serialize helper invocations for this root. External Git/Flame still
            # requires the operator to stop editing/using hooks during changes.
            root = args.root.expanduser().resolve()
            if not root.is_dir():
                raise Unsafe(f"Missing checkout parent: {root}")
            with (root / ".dgpy-dev.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise Unsafe("Another DGpy update/switch is running for this root")
                synchronize(args)
        else:
            return {"status": status, "setup": setup, "env": environment, "install": install}[args.command](args) or 0
        return 0
    except (Unsafe, OSError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
