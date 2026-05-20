import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


def build_index(home_dir: str) -> list[dict]:
    """Walk home_dir and first-level subdirectories only. Returns list of file entry dicts.

    Does NOT recurse into second-level directories.
    """
    home = Path(home_dir)
    entries = []

    # Depth 0: files directly in home
    for item in home.iterdir():
        if item.is_file(follow_symlinks=False):
            entries.append(_make_entry(item))

    # Depth 1: files in immediate subdirectories
    for subdir in home.iterdir():
        if subdir.is_dir(follow_symlinks=False):
            for item in subdir.iterdir():
                if item.is_file(follow_symlinks=False):
                    entries.append(_make_entry(item))

    return entries


def _make_entry(path: Path) -> dict:
    st = path.stat()
    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
    is_executable = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return {
        "path": str(path),
        "size": st.st_size,
        "ext": path.suffix.lower(),
        "mtime": mtime,
        "is_executable": is_executable,
    }


def save_index(entries: list[dict], index_path: str) -> None:
    with open(index_path, "w") as f:
        json.dump({"scanned_at": datetime.now(timezone.utc).isoformat(), "files": entries}, f, indent=2)


def load_index(index_path: str) -> list[dict]:
    with open(index_path) as f:
        data = json.load(f)
    return data["files"]
