"""Backup phase: drive detection + tar archive creation.

Security/safety notes:
- Refuses backup destinations that resolve inside the home directory (would cause
  the growing archive to be included in itself).
- Uses `--` separator before the home path in argv so a path starting with `-`
  cannot be reinterpreted as a tar option.
- Excludes common cache and junk directories by default.
- Uses --one-file-system so symlinked mounts (Steam libraries, network shares
  mounted under home) don't get pulled into the archive.
- Always passes a timeout to subprocess.run.
"""
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

MOUNTS_FILE = "/proc/mounts"

# Default 8 hour timeout for tar — long enough for a multi-TB home, finite enough
# that a stuck tar process doesn't hang the agent forever.
DEFAULT_TAR_TIMEOUT_SECONDS = 8 * 60 * 60

_EXCLUDED_PREFIXES = ("/sys", "/proc", "/dev", "/run/user", "/efi", "/boot")
_EXCLUDED_EXACT = {"/", "/tmp"}
_EXCLUDED_FS = {"sysfs", "proc", "devtmpfs", "devpts", "tmpfs", "cgroup",
                "cgroup2", "pstore", "bpf", "tracefs", "securityfs",
                "fusectl", "hugetlbfs", "mqueue", "debugfs", "configfs"}

# Default exclude patterns — applied relative to the home directory being archived.
# Users can pass extra patterns; these are always included.
DEFAULT_EXCLUDE_PATTERNS = (
    ".cache",
    ".local/share/Trash",
    "Trash",
    ".local/share/Steam",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".npm",
    ".yarn/cache",
    ".cargo/registry",
    ".rustup",
    ".gradle/caches",
    ".m2/repository",
    "snap",
    ".thumbnails",
    ".mozilla/firefox/*/Cache",
)


def detect_drives() -> list[dict]:
    """Return mounted user-accessible drives sorted by free space descending.

    Each entry: {"path": str, "free_gb": float, "label": str}
    """
    drives = []
    with open(MOUNTS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = re.match(r'^(/dev/\S+)\s+(.+?)\s+([a-z0-9]+)\s+(.+)$', line)
            if not match:
                continue
            device, mountpoint, fstype = match.group(1), match.group(2), match.group(3)

            if fstype in _EXCLUDED_FS:
                continue
            if mountpoint in _EXCLUDED_EXACT:
                continue
            if any(mountpoint.startswith(p) for p in _EXCLUDED_PREFIXES):
                continue
            try:
                usage = shutil.disk_usage(mountpoint)
                label = Path(mountpoint).name or mountpoint
                drives.append({
                    "path": mountpoint,
                    "free_gb": round(usage.free / 1024**3, 1),
                    "label": label,
                })
            except OSError:
                continue

    drives.sort(key=lambda d: d["free_gb"], reverse=True)
    return drives


def create_backup(
    home_dir: str,
    backup_dir: str,
    date_str: str = None,
    extra_excludes: tuple = (),
    timeout: int = DEFAULT_TAR_TIMEOUT_SECONDS,
) -> dict:
    """Create a gzipped tar archive of home_dir inside backup_dir.

    Args:
        home_dir: Path to archive (typically the user's home).
        backup_dir: Directory where the archive will be written. Must resolve to a
            path OUTSIDE home_dir.
        date_str: Optional override for the date stamp in the archive name.
        extra_excludes: Additional patterns to exclude (relative to home_dir).
            DEFAULT_EXCLUDE_PATTERNS are always applied.
        timeout: Per-process timeout in seconds.

    Returns:
        {"archive_path": str, "size_gb": float}

    Raises:
        ValueError: If backup_dir is the same as or inside home_dir.
        RuntimeError: If tar exits non-zero or times out.
    """
    home_resolved = Path(home_dir).resolve(strict=False)
    backup_resolved = Path(backup_dir).resolve(strict=False)

    # Reject destinations inside home — otherwise tar tries to archive the growing file
    if backup_resolved == home_resolved:
        raise ValueError(
            f"backup destination {backup_dir!r} is the home directory itself"
        )
    try:
        backup_resolved.relative_to(home_resolved)
    except ValueError:
        pass  # not inside home — good
    else:
        raise ValueError(
            f"backup destination {backup_dir!r} is inside home {home_dir!r}; "
            "the growing archive would be included in itself"
        )

    if date_str is None:
        date_str = date.today().isoformat()
    archive_name = f"home-backup-{date_str}.tar.gz"
    archive_path = str(Path(backup_dir) / archive_name)

    all_excludes = tuple(DEFAULT_EXCLUDE_PATTERNS) + tuple(extra_excludes)
    exclude_args = []
    for pattern in all_excludes:
        exclude_args.extend(["--exclude", pattern])

    # tar argv: czf <archive> --one-file-system <excludes> -- <home_dir>
    # The `--` separator prevents a home_dir starting with `-` from being parsed
    # as a tar option.
    cmd = (
        ["tar", "czf", archive_path, "--one-file-system"]
        + exclude_args
        + ["--", home_dir]
    )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"tar timed out after {timeout}s")

    if result.returncode != 0:
        raise RuntimeError(
            f"tar failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    size_gb = round(Path(archive_path).stat().st_size / 1024**3, 2)
    return {"archive_path": archive_path, "size_gb": size_gb}
