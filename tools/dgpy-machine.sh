#!/bin/sh
# DGpy per-machine onboarding / repeatable refresh (macOS and Linux).
# Apply is explicit. No sudo, shell-profile edits, or existing-hook replacement.
set -eu

stop() { printf 'STOP: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }
usage() {
    cat <<'EOF'
Usage: sh dgpy-machine.sh [--apply] [--shared] [--with-internal | --public-only]
       [--root ABSOLUTE_PATH] [--state-dir ABSOLUTE_PATH]
       [--hook-dir ABSOLUTE_PATH] [--check-hook-dir ABSOLUTE_PATH]...
       [--public-branch BRANCH] [--internal-branch BRANCH]

Without --apply, only checks and prints the proposed actions.
With --apply, clone missing checkouts / safely fast-forward existing ones,
install versioned DGpy commands, and link just dgpy_bootstrap.py to this
OS user's Flame Python hook directory. Never modifies Flame User loading,
other hooks, shell profiles, or existing unrelated files.
--shared uses an already existing checkout without any Git clone/fetch/update.
EOF
}

[ -n "${HOME:-}" ] || stop 'HOME must be set'
case "$(uname -s)" in Darwin|Linux) ;; *) stop 'Only macOS and Linux are supported' ;; esac
command -v git >/dev/null 2>&1 || stop 'Git is required'
root=${DGPY_ROOT:-"$HOME/DGpy"}
state=${DGPY_STATE_DIR:-"$HOME/DGpy"}
public_branch=${DGPY_PUBLIC_BRANCH:-chore/dev-workflow}
internal_branch=${DGPY_INTERNAL_BRANCH:-chore/dev-workflow}
public_url=${DGPY_PUBLIC_REMOTE:-https://github.com/71233/dg-python-scripts.git}
internal_url=${DGPY_INTERNAL_REMOTE:-https://github.com/71233/dg-python-scripts-internal.git}
internal_policy=auto
shared=no
apply=no
hook_path=
checks=
newline='
'
while [ "$#" -gt 0 ]; do
    case "$1" in
        --apply) apply=yes; shift ;;
        --shared) shared=yes; shift ;;
        --with-internal) internal_policy=yes; shift ;;
        --public-only) internal_policy=no; shift ;;
        --root|--state-dir|--hook-dir|--check-hook-dir|--public-branch|--internal-branch)
            [ "$#" -ge 2 ] && [ -n "$2" ] || stop "$1 requires a value"
            value=$2
            case "$value" in *"$newline"*) stop 'Newlines are not supported in paths/branch names' ;; esac
            case "$1" in
                --root) root=$value ;;
                --state-dir) state=$value ;;
                --hook-dir) hook_path=$value ;;
                --check-hook-dir) checks="$checks
$value" ;;
                --public-branch) public_branch=$value ;;
                --internal-branch) internal_branch=$value ;;
            esac
            shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) stop "Unknown option: $1" ;;
    esac
done
for path in "$root" "$state"; do
    case "$path" in /*) ;; *) stop "Path must be absolute: $path" ;; esac
done
[ "$root" != / ] && [ "$state" != / ] || stop 'Refusing filesystem root as DGpy directory'
if [ -d "$root" ]; then root=$(CDPATH= cd -- "$root" && pwd -P); fi
if [ -d "$state" ]; then state=$(CDPATH= cd -- "$state" && pwd -P); fi
if [ "$shared" = no ]; then
    case "$root" in "$HOME/"*) ;; *) stop "Checkout outside HOME may be shared: use --shared (no Git updates)" ;; esac
fi
if [ -n "$hook_path" ]; then
    case "$hook_path" in /*) ;; *) stop '--hook-dir must be absolute' ;; esac
fi
for branch in "$public_branch" "$internal_branch"; do
    git check-ref-format --branch "$branch" >/dev/null 2>&1 || stop "Invalid branch: $branch"
done

public="$root/dg-python-scripts"
internal="$root/dg-python-scripts-internal"
versions="$state/.dgpy-tool-versions"
current="$state/bin-managed"
config="$state/site.toml"

# Inspect every existing checkout before creating or modifying anything.
check_repo() {
    directory=$1
    name=$2
    expected=$3
    if [ -e "$directory" ] || [ -L "$directory" ]; then
        [ ! -L "$directory" ] && [ -d "$directory" ] || stop "$name: existing path is not a checkout directory"
        top=$(git -C "$directory" rev-parse --show-toplevel 2>/dev/null) || stop "$name: not a Git checkout"
        [ "$top" = "$directory" ] || stop "$name: checkout root is unexpected"
        origin=$(git -C "$directory" remote get-url origin 2>/dev/null) || stop "$name: missing origin"
        case "$origin" in
            "$expected"|"https://github.com/71233/$name"|"https://github.com/71233/$name.git"|"git@github.com:71233/$name.git"|"ssh://git@github.com/71233/$name.git") ;;
            *) stop "$name: origin does not match expected repository" ;;
        esac
        git -C "$directory" symbolic-ref --quiet HEAD >/dev/null 2>&1 || stop "$name: detached HEAD"
        [ -z "$(git -C "$directory" status --porcelain --untracked-files=all)" ] || stop "$name: working tree is dirty"
        note "$name: existing clean checkout (branch preserved)"
    else
        note "$name: will clone branch $4"
    fi
}
if [ "$shared" = yes ] && [ ! -d "$public" ]; then stop "Shared checkout missing: $public"; fi
check_repo "$public" dg-python-scripts "$public_url" "$public_branch"
include_internal=no
if [ "$internal_policy" = yes ] || { [ "$internal_policy" = auto ] && { [ -e "$internal" ] || [ -L "$internal" ]; }; }; then
    include_internal=yes
    if [ "$shared" = yes ] && [ ! -d "$internal" ]; then stop "Shared checkout missing: $internal"; fi
    check_repo "$internal" dg-python-scripts-internal "$internal_url" "$internal_branch"
fi
if [ "$include_internal" = yes ]; then
    if [ -L "$config" ] || { [ -e "$config" ] && [ ! -f "$config" ]; }; then
        stop "Existing Internal configuration protected: $config"
    fi
fi
# No overwriting foreign command directories / symlinks.
if [ -e "$current" ] || [ -L "$current" ]; then
    [ -L "$current" ] || stop "Existing command path protected: $current"
    old=$(readlink "$current")
    case "$old" in "$versions/"*) ;; *) stop "Foreign command symlink protected: $current" ;; esac
fi
# Same user-level hook path on all runs unless explicitly overridden.
if [ -z "$hook_path" ]; then
    case "$(uname -s)" in
        Darwin) hook_path="$HOME/Library/Preferences/Autodesk/flame/python" ;;
        Linux) hook_path="$HOME/flame/python" ;;
    esac
fi
note "Checkout root: $root"
note "Local tools:   $current"
note "User hook:     $hook_path/dgpy_bootstrap.py"
note "Scope:         public$( [ "$include_internal" = yes ] && printf ' + internal' || true )"
if [ "$shared" = yes ]; then note "Mode:          attach only; Git will not be changed"; fi
if [ "$apply" != yes ]; then
    note 'PREVIEW ONLY: pass --apply to clone/update and create a missing user hook.'
    exit 0
fi
# All local mutable state is under user-owned paths. Do not edit shell profiles.
mkdir -p "$root" "$state"
root=$(CDPATH= cd -- "$root" && pwd -P)
state=$(CDPATH= cd -- "$state" && pwd -P)
public="$root/dg-python-scripts"
internal="$root/dg-python-scripts-internal"
versions="$state/.dgpy-tool-versions"
current="$state/bin-managed"
config="$state/site.toml"
lock="$state/.dgpy-machine.lock"
mkdir "$lock" 2>/dev/null || stop "Another machine setup may be running: $lock"
next_link="$state/.dgpy-bin-next-$$"
cleanup() {
    [ ! -L "$next_link" ] || rm "$next_link"
    rmdir "$lock" 2>/dev/null || true
}
trap cleanup 0
trap 'exit 1' 1 2 3 15

[ "$shared" = yes ] || {
    if [ ! -d "$public" ]; then
        git clone --branch "$public_branch" "$public_url" "$public"
    fi
    if [ "$include_internal" = yes ] && [ ! -d "$internal" ]; then
        git clone --branch "$internal_branch" "$internal_url" "$internal"
    fi
}
[ -f "$public/tools/dgpy" ] || stop 'Public checkout lacks tools/dgpy; use chore/dev-workflow until launcher is merged'
repo_scope=public
[ "$include_internal" = no ] || repo_scope=all
if [ "$shared" = no ]; then
    /bin/sh "$public/tools/dgpy" update --root "$root" --repo "$repo_scope"
fi
# Clone/update first, then validate hook targets. Existing links are protected.
set --
[ -z "$hook_path" ] || set -- "$@" --hook-dir "$hook_path"
old_ifs=$IFS
IFS='
'
for check in $checks; do
    [ -z "$check" ] || set -- "$@" --check-hook-dir "$check"
done
IFS=$old_ifs
/bin/sh "$public/tools/dgpy" setup --root "$root" "$@" --apply
/bin/sh "$public/tools/dgpy" status --root "$root" --repo "$repo_scope" "$@"
if [ "$include_internal" = yes ]; then
    if [ -L "$config" ]; then stop "Config symlink protected: $config"; fi
    if [ ! -e "$config" ]; then
        # Only create a non-existent user-owned example. Never replace site config.
        (umask 077; set -C; cat "$internal/examples/dgpy.toml" > "$config") || stop 'Could not create site config safely'
        note "Created local Internal TOML: $config"
    fi
fi
sha=$(git -C "$public" rev-parse HEAD)
case "$sha" in *[!0-9a-f]*|'') stop 'Invalid public commit' ;; esac
mkdir -p "$versions"
version_dir="$versions/$sha"
/bin/sh "$public/tools/dgpy" install --bin-dir "$version_dir" --apply
[ ! -e "$next_link" ] && [ ! -L "$next_link" ] || stop "Temporary link already exists: $next_link"
ln -s "$version_dir" "$next_link"
# os.replace replaces the symlink itself, never follows a directory-symlink target.
if [ -n "${DGPY_PYTHON:-}" ]; then
    python=$DGPY_PYTHON
elif [ -x /opt/Autodesk/python/2025.2.7/bin/python3 ]; then
    python=/opt/Autodesk/python/2025.2.7/bin/python3
else
    python=$(command -v python3 || true)
fi
[ -n "$python" ] && [ -x "$python" ] || stop 'Python executable unavailable for safe tool switch'
# Recheck before switching; only our managed link may be replaced.
if [ -e "$current" ] || [ -L "$current" ]; then
    [ -L "$current" ] || stop "Existing command path protected: $current"
    old=$(readlink "$current")
    case "$old" in "$versions/"*) ;; *) stop "Foreign command symlink protected: $current" ;; esac
fi
"$python" -I -c 'import os,sys; os.replace(sys.argv[1],sys.argv[2])' "$next_link" "$current"
note "READY: $current/dgpy-status"
note "START: $current/dgpy-flame --dry-run"
if [ "$include_internal" = yes ]; then
    note "INTERNAL: $current/dgpy-flame --with-internal --config $config --dry-run"
fi
note 'Restart Flame after a source/config change. Normal GUI launch does not inherit launcher-only PYTHONPATH.'
