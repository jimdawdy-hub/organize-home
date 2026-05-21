"""Image rename script.

CLI modes:
  --scan <pictures_dir>         Print JSON list of non-descriptive images
  --rename <old_path> <new_stem> Rename file to new_stem (collision-safe)
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}

_CAMERA_PATTERNS = re.compile(
    r"^(IMG|DSC|DCIM|PICT|PHOTO)_?\d+$", re.IGNORECASE
)
_ALL_DIGITS = re.compile(r"^\d+$")


def is_non_descriptive(stem: str) -> bool:
    """Return True if the filename stem is considered non-descriptive."""
    if _ALL_DIGITS.match(stem):
        return True
    if len(stem) < 6:
        return True
    if _CAMERA_PATTERNS.match(stem):
        return True
    return False


def get_exif_date(path: str) -> str | None:
    """Return YYYY-MM-DD from EXIF DateTimeOriginal, or None.

    Bounded at 10s — a malformed image can hang exiftool indefinitely.
    """
    try:
        result = subprocess.run(
            ["exiftool", "-DateTimeOriginal", "-s3", "--", path],
            capture_output=True, text=True, timeout=10
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    raw = result.stdout.strip()  # e.g. "2023:06:15 14:30:00"
    try:
        dt = datetime.strptime(raw[:10], "%Y:%m:%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def get_mtime_date(path: str) -> str:
    """Return YYYY-MM-DD from file modification time."""
    mtime = Path(path).stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def make_unique_stem(directory: Path, stem: str, ext: str) -> str:
    """Return a collision-free stem like YYYY-MM-DD_001."""
    counter = 1
    while True:
        candidate = f"{stem}_{counter:03d}"
        if not (directory / f"{candidate}{ext}").exists():
            return candidate
        counter += 1


def scan_for_rename(pictures_dir: str) -> list[dict]:
    """Return list of {path, exif_date} for non-descriptive images."""
    results = []
    for item in Path(pictures_dir).iterdir():
        if item.suffix.lower() not in IMAGE_EXTS:
            continue
        if not is_non_descriptive(item.stem):
            continue
        exif_date = get_exif_date(str(item))
        results.append({"path": str(item), "exif_date": exif_date})
    return results


def do_rename(old_path: str, new_stem: str) -> str:
    """Rename file to new_stem, collision-safe. Returns new path."""
    old = Path(old_path)
    new_path = old.parent / f"{new_stem}{old.suffix.lower()}"
    if new_path.exists() and new_path != old:
        new_stem = make_unique_stem(old.parent, new_stem, old.suffix.lower())
        new_path = old.parent / f"{new_stem}{old.suffix.lower()}"
    old.rename(new_path)
    return str(new_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: rename_images.py --scan <dir> | --rename <old> <new_stem>")
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "--scan":
        results = scan_for_rename(sys.argv[2])
        print(json.dumps(results, indent=2))
    elif mode == "--rename":
        new_path = do_rename(sys.argv[2], sys.argv[3])
        print(json.dumps({"new_path": new_path}))
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
