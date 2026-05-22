import shutil
import re
from pathlib import Path

try:
    from scripts.safety import is_safe_destination, is_within_home
except ImportError:
    from safety import is_safe_destination, is_within_home

ARCHIVE_EXTS = {".zip", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tar"}
EMAIL_EXTS = {".eml", ".msg"}
EBOOK_EXTS = {".epub", ".mobi", ".azw3"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}

_DOWNLOAD_FILENAME_RULES = (
    ("financial:wells fargo", "Financial", ("wells fargo", "wellsfargo")),
    ("legal_reference:case citation", "Legal Reference", (" v ", " v. ", "ill. app.", "ill.")),
    ("hamradio:dmr", "HamRadio", ("dmr",)),
    ("correspondence:letter", "Correspondence", ("letter",)),
    ("career:dawdy cv", "Career", ("dawdy cv", "cv dawdy")),
    (
        "medmal:work filename",
        "Medical Files",
        ("med recs", "med rec", "bills", "deposition", "transcript"),
    ),
    (
        "legal:litigation filename",
        "Legal Filings",
        (
            "motion",
            "order",
            "orders",
            "advocate",
            "pltf",
            "court",
            "ct",
            "def",
            "plainitff",
            "response",
        ),
    ),
)

_IMAGE_SOURCE_DIRS = {"downloads", "documents"}


def _matches_substring(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def get_destination(entry: dict, home_dir: str) -> tuple[str, str] | None:
    """Return (destination_directory, rule_name) or None if no rule matches.

    Rules are checked in order; first match wins.
    """
    home = Path(home_dir)
    path = Path(entry["path"])
    ext = entry["ext"].lower()
    parent_name = path.parent.name.lower()
    filename_haystack = path.name.lower()

    if parent_name == "downloads":
        for rule_name, folder, needles in _DOWNLOAD_FILENAME_RULES:
            if rule_name == "career:dawdy cv":
                if _matches_substring(filename_haystack, ("dawdy",)) and _matches_substring(filename_haystack, ("cv",)):
                    return str(home / folder), rule_name
                continue
            if _matches_substring(filename_haystack, needles):
                return str(home / folder), rule_name

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
    """Apply rule-based moves. Returns list of entries that were NOT routed.

    Safety guards:
    - Source must resolve to a path inside home (rejects symlink-escapes).
    - Destination must pass is_safe_destination (inside home, no dotdir components).
    - Any rejected file is logged as an error and skipped, not moved.
    """
    unrouted = []

    for entry in entries:
        result = get_destination(entry, home_dir)
        if result is None:
            unrouted.append(entry)
            continue

        dest_dir, rule = result
        src = Path(entry["path"])

        # Source-safety: source path (after resolving) must be inside home
        if not is_within_home(src, home_dir):
            state.add_error(str(src), f"refused move: source resolves outside home")
            continue

        # Destination-safety: dest must be a safe location under home
        if not is_safe_destination(dest_dir, home_dir):
            state.add_error(str(src), f"refused move: destination {dest_dir!r} is unsafe")
            continue

        dest_path = Path(dest_dir) / src.name

        if src == dest_path:
            continue

        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        dest_path = _atomic_unique_path(dest_path)

        try:
            _safe_move(src, dest_path)
        except OSError as exc:
            state.add_error(str(src), f"move failed: {exc}")
            continue

        state.add_move(str(src), str(dest_path), phase=3, rule=rule)

    return unrouted


def _atomic_unique_path(dest_path: Path) -> Path:
    """Return a collision-free Path by atomically reserving it via O_CREAT|O_EXCL.

    Closes the TOCTOU race in the previous `while exists(): counter += 1` loop —
    another process could have created the file between the existence check and
    the move. This function actually claims the name by creating an empty file
    with O_EXCL, then returns the reserved path so the caller can overwrite it.
    """
    import os
    stem, suffix = dest_path.stem, dest_path.suffix
    candidate = dest_path
    counter = 0
    while True:
        try:
            fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return candidate
        except FileExistsError:
            counter += 1
            candidate = dest_path.parent / f"{stem}_{counter}{suffix}"
            if counter > 10000:
                raise RuntimeError(f"cannot find unique name for {dest_path}")


def _safe_move(src: Path, dest: Path) -> None:
    """Move src → dest. Uses atomic rename when on the same filesystem; otherwise
    copies with verification before deleting source to avoid mid-copy data loss.

    `dest` is expected to be a path already reserved by `_atomic_unique_path`,
    so we remove the placeholder before renaming/copying onto it.
    """
    import os
    # Remove the empty placeholder reserved by _atomic_unique_path
    try:
        if dest.exists() and dest.stat().st_size == 0:
            dest.unlink()
    except OSError:
        pass

    try:
        os.rename(str(src), str(dest))
        return
    except OSError as exc:
        # EXDEV (cross-device) is the expected case for fallback; any other
        # error should propagate.
        import errno
        if exc.errno != errno.EXDEV:
            raise

    # Cross-filesystem: copy with verification, then delete source.
    src_size = src.stat().st_size
    shutil.copy2(str(src), str(dest))
    if dest.stat().st_size != src_size:
        # Partial copy — leave source intact for recovery
        try:
            dest.unlink()
        except OSError:
            pass
        raise OSError(f"cross-fs copy size mismatch for {src} -> {dest}")
    src.unlink()
