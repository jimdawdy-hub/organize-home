import shutil
from pathlib import Path

ARCHIVE_EXTS = {".zip", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tar"}
EMAIL_EXTS = {".eml", ".msg"}
EBOOK_EXTS = {".epub", ".mobi", ".azw3"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}

_IMAGE_SOURCE_DIRS = {"downloads", "documents"}


def get_destination(entry: dict, home_dir: str) -> tuple[str, str] | None:
    """Return (destination_directory, rule_name) or None if no rule matches.

    Rules are checked in order; first match wins.
    """
    home = Path(home_dir)
    path = Path(entry["path"])
    ext = entry["ext"].lower()
    parent_name = path.parent.name.lower()

    # Archives — match anywhere under home
    if ext in ARCHIVE_EXTS:
        return str(home / "Zip Archive"), "archive"

    # Emails — match anywhere
    if ext in EMAIL_EXTS:
        return str(home / "Emails"), "email"

    # Ebooks — match anywhere
    if ext in EBOOK_EXTS:
        return str(home / "Books"), "ebook"

    # Executables — only in Downloads
    if entry.get("is_executable") and parent_name == "downloads":
        return str(home / "Downloads" / "ExecFiles"), "executable"

    # Images — only from home root, Downloads, or Documents; skip if already in Pictures
    if ext in IMAGE_EXTS:
        if parent_name == "pictures" or path.parent == home / "Pictures":
            return None
        if path.parent == home or parent_name in _IMAGE_SOURCE_DIRS:
            return str(home / "Pictures"), "image"

    return None


def apply_moves(entries: list[dict], home_dir: str, state) -> list[dict]:
    """Apply rule-based moves. Returns list of entries that were NOT routed (need AI review)."""
    home = Path(home_dir)
    unrouted = []

    for entry in entries:
        result = get_destination(entry, home_dir)
        if result is None:
            unrouted.append(entry)
            continue

        dest_dir, rule = result
        src = Path(entry["path"])
        dest_path = Path(dest_dir) / src.name

        if src == dest_path:
            continue

        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        # Avoid clobbering existing files with the same name
        if dest_path.exists():
            stem, suffix = dest_path.stem, dest_path.suffix
            counter = 1
            while dest_path.exists():
                dest_path = Path(dest_dir) / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.move(str(src), str(dest_path))
        state.add_move(str(src), str(dest_path), phase=3, rule=rule)

    return unrouted
