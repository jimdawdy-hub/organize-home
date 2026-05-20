import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

MOUNTS_FILE = "/proc/mounts"

_EXCLUDED_PREFIXES = ("/sys", "/proc", "/dev", "/run/user", "/efi", "/boot")
_EXCLUDED_EXACT = {"/", "/tmp"}
_EXCLUDED_FS = {"sysfs", "proc", "devtmpfs", "devpts", "tmpfs", "cgroup",
                "cgroup2", "pstore", "bpf", "tracefs", "securityfs",
                "fusectl", "hugetlbfs", "mqueue", "debugfs", "configfs"}


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
            # Parse: device mountpoint fstype options...
            # Use regex to handle spaces in mountpoint. Fstype is [a-z0-9]+ pattern
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
            if not device.startswith("/dev/"):
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


def create_backup(home_dir: str, backup_dir: str, date_str: str = None) -> dict:
    """Create a gzipped tar archive of home_dir inside backup_dir.

    Returns {"archive_path": str, "size_gb": float}
    Raises RuntimeError if tar exits non-zero.
    """
    if date_str is None:
        date_str = date.today().isoformat()
    archive_name = f"home-backup-{date_str}.tar.gz"
    archive_path = str(Path(backup_dir) / archive_name)

    cmd = ["tar", "czf", archive_path, home_dir]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"tar failed (exit {result.returncode}): {result.stderr.strip()}")

    size_gb = round(Path(archive_path).stat().st_size / 1024**3, 2)
    return {"archive_path": archive_path, "size_gb": size_gb}
