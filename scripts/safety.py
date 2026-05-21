"""Path safety helpers.

These functions guard against three classes of bug:

1. **Out-of-home writes** — an AI-returned folder, a malicious state file, or a
   bad symlink can name a path that resolves outside the user's home directory.
2. **Dotfile clobbering** — moving files into or out of ~/.ssh/, ~/.gnupg/,
   ~/.config/, etc. can break authentication, password stores, app config.
3. **Symlink-based path traversal** — `~/Documents/photo.jpg` could be a symlink
   pointing to `/etc/passwd`; naive code would move the target.

All consumers MUST validate any path that comes from outside `safety.py`'s own
module before writing/moving. `is_safe_destination` is the strictest check and
is the right default for categorization destinations.
"""
from pathlib import Path

# Dot-directories that must never be written to as categorization destinations.
# A user's SSH keys, GPG keyring, etc. live here — moving files in/out breaks them.
_BLOCKLIST_DIRS = frozenset({
    ".ssh", ".gnupg", ".gnupg2", ".password-store", ".pgp",
    ".aws", ".kube", ".docker",
    ".config", ".local", ".cache",
    ".mozilla", ".thunderbird", ".chromium", ".chrome", ".firefox",
    ".git",  # never disturb a git repo at home root
})


def is_hidden(path) -> bool:
    """Return True if any component of `path` starts with a dot.

    Accepts a relative Path or a Path-like. Caller is responsible for passing
    a relative path (typically `absolute_path.relative_to(home_dir)`).
    """
    return any(part.startswith(".") for part in Path(path).parts)


def is_within_home(candidate, home_dir) -> bool:
    """Return True if `candidate` (after symlink resolution) is inside `home_dir`,
    excluding paths that traverse a blocklisted dot-directory.

    Returns False on any error resolving the path (broken symlink, permission denied,
    nonexistent home). This is the conservative default for safety checks.
    """
    try:
        home = Path(home_dir).resolve(strict=False)
        cand = Path(candidate).resolve(strict=False)
    except (OSError, RuntimeError):
        return False

    if cand == home:
        return True

    try:
        rel = cand.relative_to(home)
    except ValueError:
        return False

    for part in rel.parts:
        if part in _BLOCKLIST_DIRS:
            return False

    return True


def is_safe_destination(dest_dir, home_dir) -> bool:
    """Return True if dest_dir is acceptable as a write/move destination.

    Stricter than `is_within_home`: rejects ANY dot-prefixed component, not just
    blocklisted ones. Use this for categorization destinations where the only
    legitimate targets are visible (non-hidden) folders under the user's home.
    """
    try:
        home = Path(home_dir).resolve(strict=False)
        dest = Path(dest_dir).resolve(strict=False)
    except (OSError, RuntimeError):
        return False

    if dest == home:
        return True

    try:
        rel = dest.relative_to(home)
    except ValueError:
        return False

    for part in rel.parts:
        if part.startswith("."):
            return False

    return True
