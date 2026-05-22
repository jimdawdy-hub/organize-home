"""Workflow runner that resumes organize-home from the next incomplete phase."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from scripts.ai_review import classify_document_text, extract_first_page
    from scripts.categorize import apply_moves
    from scripts.html_report import generate_report
    from scripts.index_files import build_index, load_index, save_index
    from scripts.rename_images import do_rename, get_mtime_date, scan_for_rename
    from scripts.safety import is_safe_destination, is_within_home
    from scripts.state import StateManager
except ImportError:  # pragma: no cover - support direct script execution
    from ai_review import classify_document_text, extract_first_page
    from categorize import apply_moves
    from html_report import generate_report
    from index_files import build_index, load_index, save_index
    from rename_images import do_rename, get_mtime_date, scan_for_rename
    from safety import is_safe_destination, is_within_home
    from state import StateManager


INDEX_PATH = ".organize-home-index.json"
UNROUTED_PATH = "/tmp/unrouted.json"
HTML_REPORT_PATH = "home-index.html"
BACKUP_SEARCH_ROOTS = (
    "/mnt",
    "/run/media",
    "/media",
    "/tmp",
)


def _next_phase(completed: list[int]) -> int:
    for phase in range(2, 9):
        if phase not in completed:
            return phase
    return 9


def _iter_backup_candidates(root: Path, max_depth: int = 4):
    if not root.exists():
        return
    root_depth = len(root.parts)
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            depth = len(current.parts) - root_depth
            if depth > max_depth:
                continue
            for item in current.iterdir():
                if item.is_symlink():
                    continue
                if item.is_file() and item.name.startswith("home-backup-") and item.name.endswith(".tar.gz"):
                    yield item
                elif item.is_dir() and depth < max_depth:
                    stack.append(item)
        except OSError:
            continue


def find_latest_backup(search_roots: tuple[str, ...] = BACKUP_SEARCH_ROOTS) -> Path | None:
    candidates = []
    for root in search_roots:
        for path in _iter_backup_candidates(Path(root)):
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > 0:
                candidates.append((stat.st_mtime, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _resolve_bootstrap_backup(bootstrap_backup: str | None) -> Path | None:
    if bootstrap_backup is None:
        return None
    if bootstrap_backup == "auto":
        return find_latest_backup()
    backup = Path(bootstrap_backup).expanduser()
    if not backup.exists():
        raise RuntimeError(f"backup archive not found: {backup}")
    if not backup.is_file() or backup.stat().st_size <= 0:
        raise RuntimeError(f"backup archive is not a non-empty file: {backup}")
    return backup


def _bootstrap_after_backup(state: StateManager, backup_path: Path) -> None:
    state.set_backup_path(str(backup_path))
    state.mark_phase_complete(0)
    state.mark_phase_complete(1)
    print(f"Bootstrapped state from backup: {backup_path}")


def _run_phase_2(home_dir: Path, state: StateManager) -> int:
    entries = build_index(str(home_dir))
    save_index(entries, str(home_dir / INDEX_PATH))
    state.mark_phase_complete(2)
    print(f"Indexed {len(entries)} files")
    return 2


def _run_phase_3(home_dir: Path, state: StateManager) -> int:
    entries = load_index(str(home_dir / INDEX_PATH))
    unrouted = apply_moves(entries, str(home_dir), state)
    with open(UNROUTED_PATH, "w") as f:
        json.dump(unrouted, f, indent=2)
    state.mark_phase_complete(3)
    print(f"Moved {len(entries) - len(unrouted)} files. {len(unrouted)} need AI review.")
    return 3


def _run_phase_4(home_dir: Path, state: StateManager) -> int:
    pictures = home_dir / "Pictures"
    results = scan_for_rename(str(pictures))
    for item in results:
        exif_date = item.get("exif_date")
        path = item.get("path")
        if not path:
            continue
        new_stem = exif_date or get_mtime_date(path)
        do_rename(path, new_stem)
    state.mark_phase_complete(4)
    print(f"Scanned {len(results)} images for renaming")
    return 4


def _unique_destination(dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        next_candidate = dest_dir / f"{stem}_{counter}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        counter += 1


def _move_reviewed_file(path: str, folder: str, home_dir: Path) -> str:
    src = Path(path)
    if not is_within_home(src, str(home_dir)):
        raise ValueError("source resolves outside home")
    if not is_safe_destination(folder, str(home_dir)):
        raise ValueError(f"destination is unsafe: {folder}")
    dest = _unique_destination(Path(folder), src.name)
    shutil.move(str(src), str(dest))
    return str(dest)


def _classify_and_route_document(path: str, home_dir: Path, state: StateManager) -> str:
    text = extract_first_page(path)
    result = classify_document_text(text, path, str(home_dir))
    confidence = float(result.get("confidence", 0.0))
    folder = result.get("folder") or ""
    category = result.get("category") or "Uncategorized"
    reason = result.get("reason") or "no reason provided"

    if confidence > 0.5 and folder:
        try:
            dest = _move_reviewed_file(path, folder, home_dir)
        except (OSError, ValueError) as exc:
            state.add_low_confidence(path, folder, confidence, f"move refused: {exc}; {reason}")
            return "queued"
        state.add_move(path, dest, phase=5, rule=f"ai:{category}")
        return "moved"

    state.add_low_confidence(path, folder, confidence, reason)
    return "queued"


def _run_phase_5(home_dir: Path, state: StateManager) -> int:
    unrouted_path = Path(UNROUTED_PATH)
    if not unrouted_path.exists():
        print("No unrouted files found; skipping AI review.")
        state.mark_phase_complete(5)
        return 5

    with unrouted_path.open() as f:
        unrouted = json.load(f)

    reviewable_exts = {".pdf", ".doc", ".docx", ".txt", ".md", ".odt", ".rtf"}
    classified = 0
    queued = 0
    for entry in unrouted:
        path = entry.get("path")
        if not path:
            continue
        if Path(path).suffix.lower() not in reviewable_exts:
            continue
        status = _classify_and_route_document(path, home_dir, state)
        if status == "moved":
            classified += 1
        else:
            queued += 1

    state.mark_phase_complete(5)
    print(f"Classified and moved {classified} documents. Queued {queued} for review.")
    return 5


def reprocess_review_queue(home_dir: str | None = None, state_path: str | None = None) -> dict:
    home = Path(home_dir or Path.home())
    state = StateManager(state_path) if state_path else StateManager()
    data = state.load()
    original_queue = data.get("low_confidence", []) or []
    reviewable_exts = {".pdf", ".doc", ".docx", ".txt", ".md", ".odt", ".rtf"}

    # Remove the old placeholder queue first; unresolved files are added back
    # with the classifier's actual confidence and reason.
    data["low_confidence"] = []
    state.save(data)

    moved = 0
    queued = 0
    skipped = 0
    for item in original_queue:
        path = item.get("path", "")
        if not path or Path(path).suffix.lower() not in reviewable_exts or not Path(path).exists():
            skipped += 1
            continue
        status = _classify_and_route_document(path, home, state)
        if status == "moved":
            moved += 1
        else:
            queued += 1

    generate_report(state.load(), str(home), str(home / HTML_REPORT_PATH))
    print(f"Reprocessed review queue: moved {moved}, queued {queued}, skipped {skipped}.")
    return {"moved": moved, "queued": queued, "skipped": skipped}


def _run_phase_6(home_dir: Path, state: StateManager) -> int:
    generate_report(state.load(), str(home_dir), str(home_dir / HTML_REPORT_PATH))
    state.mark_phase_complete(6)
    print(f"Wrote {home_dir / HTML_REPORT_PATH}")
    return 6


def _run_phase_7(home_dir: Path, state: StateManager) -> bool:
    low_conf = state.load().get("low_confidence", []) or []
    if not low_conf:
        return False
    print(
        f"Open file://{home_dir / HTML_REPORT_PATH} - the amber section lists "
        f"{len(low_conf)} uncertain files."
    )
    return True


def _run_phase_8(home_dir: Path, state: StateManager) -> int:
    generate_report(state.load(), str(home_dir), str(home_dir / HTML_REPORT_PATH))
    state.clear()
    print(f"Done. Browse your organized home at file://{home_dir / HTML_REPORT_PATH}")
    return 8


def resume_workflow(
    home_dir: str | None = None,
    state_path: str | None = None,
    bootstrap_backup: str | None = None,
) -> dict:
    home = Path(home_dir or Path.home())
    state = StateManager(state_path) if state_path else StateManager()
    data = state.load()

    backup_path = _resolve_bootstrap_backup(bootstrap_backup)
    if backup_path and (1 not in data["completed_phases"] or not data.get("backup_path")):
        _bootstrap_after_backup(state, backup_path)
        data = state.load()

    if 1 in data["completed_phases"] and data.get("backup_path"):
        print("Resuming from phase 2.")
    else:
        raise RuntimeError(
            "backup phase is not marked complete; this runner resumes only after backup"
        )

    next_phase = _next_phase(data["completed_phases"])
    completed = []
    for phase in range(next_phase, 9):
        if phase == 2:
            completed.append(_run_phase_2(home, state))
        elif phase == 3:
            completed.append(_run_phase_3(home, state))
        elif phase == 4:
            completed.append(_run_phase_4(home, state))
        elif phase == 5:
            completed.append(_run_phase_5(home, state))
        elif phase == 6:
            completed.append(_run_phase_6(home, state))
        elif phase == 7:
            if _run_phase_7(home, state):
                break
        elif phase == 8:
            completed.append(_run_phase_8(home, state))
    return {"next_phase": next_phase, "completed": completed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--state", default=None)
    parser.add_argument(
        "--reprocess-review",
        action="store_true",
        help="re-read and classify the current low-confidence review queue",
    )
    parser.add_argument(
        "--bootstrap-backup",
        nargs="?",
        const="auto",
        default=None,
        help=(
            "rebuild phase-1 state from an existing backup archive; "
            "omit the value to search common mount paths"
        ),
    )
    args = parser.parse_args()
    if args.reprocess_review:
        reprocess_review_queue(args.home, args.state)
        return 0
    resume_workflow(args.home, args.state, args.bootstrap_backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
