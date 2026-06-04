# organize-home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-platform (Claude Code, OpenClaw, Hermes) skill that organizes a Linux home directory with backup, rule-based file sorting, AI document categorization, and a browsable HTML index report.

**Architecture:** Shared Python scripts handle all file system operations and state management; three platform-specific SKILL.md files orchestrate the agent through 9 phases. The agent acts as the AI decision layer (image description, document categorization) and calls scripts for all deterministic operations. All scripts reference `~/organize-home/scripts/` directly. Progress is checkpointed to `~/.organize-home-state.json`.

**Tech Stack:** Python 3.10+, pypdf, python-docx, Pillow, exiftool (system binary), pytest, tar (system binary)

---

## File Map

| File | Responsibility |
|------|---------------|
| `scripts/state.py` | Read/write/clear `~/.organize-home-state.json`; single source of truth for run progress |
| `scripts/backup.py` | Detect mounted drives, prompt for backup path, create tar archive |
| `scripts/index_files.py` | Walk home dir + first-level subdirs only; output JSON index |
| `scripts/categorize.py` | Rule-based file sorting (no AI); moves zips, emails, epubs, executables, images |
| `scripts/rename_images.py` | Scan Pictures dir for non-descriptive names; rename via EXIF → AI → mtime chain |
| `scripts/ai_review.py` | Extract first-page text from PDFs/DOCX/text files; record agent's categorization result |
| `scripts/html_report.py` | Generate/update `~/home-index.html` from state data |
| `references/rules.md` | Categorization rules reference loaded by agent on demand |
| `claude/SKILL.md` | Claude Code skill — orchestrates all phases |
| `openclaw/SKILL.md` | OpenClaw skill — same logic + `metadata.openclaw` frontmatter + vision self-test |
| `hermes/SKILL.md` | Hermes skill — same logic + `fallback_for_toolsets: [vision]` + config key |
| `tests/conftest.py` | Shared pytest fixtures (fake home dir, fake state file) |
| `tests/test_state.py` | Tests for state.py |
| `tests/test_backup.py` | Tests for backup.py drive detection and tar invocation |
| `tests/test_index_files.py` | Tests for index_files.py depth limiting |
| `tests/test_categorize.py` | Tests for rule-based routing |
| `tests/test_rename_images.py` | Tests for non-descriptive name detection and rename chain |
| `tests/test_ai_review.py` | Tests for first-page text extraction |
| `tests/test_html_report.py` | Tests for HTML output structure |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Ignore venv, pycache, state files |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pytest.ini`
- Create: `scripts/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
pypdf>=4.0.0
python-docx>=1.1.0
Pillow>=10.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
.pytest_cache/
~/.organize-home-state.json
~/.organize-home-index.json
```

- [ ] **Step 3: Create pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 4: Create empty package init files**

```bash
mkdir -p scripts tests
touch scripts/__init__.py tests/__init__.py
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore pytest.ini scripts/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding, deps, pytest config"
```

---

## Task 2: state.py

**Files:**
- Create: `scripts/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state.py`:

```python
import json
import pytest
from pathlib import Path
from scripts.state import StateManager


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "organize-home-state.json"


def test_default_state_when_file_missing(state_file):
    sm = StateManager(state_file)
    data = sm.load()
    assert data["version"] == 1
    assert data["completed_phases"] == []
    assert data["moves"] == []
    assert data["low_confidence"] == []
    assert data["errors"] == []
    assert data["vision"] is None


def test_mark_phase_complete(state_file):
    sm = StateManager(state_file)
    sm.mark_phase_complete(0)
    sm.mark_phase_complete(1)
    assert sm.is_phase_complete(0)
    assert sm.is_phase_complete(1)
    assert not sm.is_phase_complete(2)


def test_add_move(state_file):
    sm = StateManager(state_file)
    sm.add_move("/home/user/Downloads/a.zip", "/home/user/Zip Archive/a.zip", phase=3, rule="zip")
    data = sm.load()
    assert len(data["moves"]) == 1
    assert data["moves"][0]["from"] == "/home/user/Downloads/a.zip"
    assert data["moves"][0]["rule"] == "zip"


def test_add_low_confidence(state_file):
    sm = StateManager(state_file)
    sm.add_low_confidence("/home/user/Downloads/mystery.pdf", "/home/user/Legal", 0.3, "unclear")
    data = sm.load()
    assert len(data["low_confidence"]) == 1
    assert data["low_confidence"][0]["confidence"] == 0.3


def test_set_vision(state_file):
    sm = StateManager(state_file)
    sm.set_vision(False)
    assert sm.load()["vision"] is False


def test_set_backup_path(state_file):
    sm = StateManager(state_file)
    sm.set_backup_path("/mnt/data/backup.tar.gz")
    assert sm.load()["backup_path"] == "/mnt/data/backup.tar.gz"


def test_clear_deletes_file(state_file):
    sm = StateManager(state_file)
    sm.mark_phase_complete(0)
    sm.clear()
    assert not state_file.exists()


def test_state_persists_across_instances(state_file):
    sm1 = StateManager(state_file)
    sm1.mark_phase_complete(3)
    sm2 = StateManager(state_file)
    assert sm2.is_phase_complete(3)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/organize-home && python -m pytest tests/test_state.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `scripts.state` does not exist yet.

- [ ] **Step 3: Implement scripts/state.py**

```python
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STATE = {
    "version": 1,
    "started_at": None,
    "backup_path": None,
    "vision": None,
    "completed_phases": [],
    "moves": [],
    "low_confidence": [],
    "errors": [],
}


class StateManager:
    def __init__(self, path: Path | str = None):
        if path is None:
            path = Path.home() / ".organize-home-state.json"
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return dict(DEFAULT_STATE)
        with self.path.open() as f:
            data = json.load(f)
        # Backfill any missing keys from DEFAULT_STATE
        for k, v in DEFAULT_STATE.items():
            data.setdefault(k, v)
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(self.path)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def mark_phase_complete(self, phase: int) -> None:
        data = self.load()
        if phase not in data["completed_phases"]:
            data["completed_phases"].append(phase)
        if data["started_at"] is None:
            data["started_at"] = datetime.now(timezone.utc).isoformat()
        self.save(data)

    def is_phase_complete(self, phase: int) -> bool:
        return phase in self.load()["completed_phases"]

    def add_move(self, from_path: str, to_path: str, phase: int, rule: str) -> None:
        data = self.load()
        data["moves"].append({"from": from_path, "to": to_path, "phase": phase, "rule": rule})
        self.save(data)

    def add_low_confidence(self, path: str, proposed: str, confidence: float, reason: str) -> None:
        data = self.load()
        data["low_confidence"].append({
            "path": path, "proposed": proposed,
            "confidence": confidence, "reason": reason,
        })
        self.save(data)

    def add_error(self, path: str, error: str) -> None:
        data = self.load()
        data["errors"].append({"path": path, "error": error})
        self.save(data)

    def set_vision(self, available: bool) -> None:
        data = self.load()
        data["vision"] = available
        self.save(data)

    def set_backup_path(self, path: str) -> None:
        data = self.load()
        data["backup_path"] = path
        self.save(data)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/organize-home && python -m pytest tests/test_state.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat: state.py — resumable run progress manager"
```

---

## Task 3: backup.py

**Files:**
- Create: `scripts/backup.py`
- Create: `tests/test_backup.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backup.py`:

```python
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.backup import detect_drives, create_backup


def test_detect_drives_parses_proc_mounts(tmp_path):
    fake_mounts = """\
sysfs /sys sysfs rw 0 0
proc /proc proc rw 0 0
/dev/sda3 /run/media/user/Linux Half 2TB ext4 rw 0 0
/dev/nvme0n1p2 / ext4 rw 0 0
tmpfs /tmp tmpfs rw 0 0
/dev/sda4 /mnt/data ext4 rw 0 0
"""
    mounts_file = tmp_path / "mounts"
    mounts_file.write_text(fake_mounts)

    with patch("scripts.backup.MOUNTS_FILE", str(mounts_file)):
        with patch("scripts.backup.shutil.disk_usage") as mock_du:
            mock_du.return_value = MagicMock(free=10 * 1024**3)
            drives = detect_drives()

    paths = [d["path"] for d in drives]
    assert "/mnt/data" in paths
    assert "/run/media/user/Linux Half 2TB" in paths
    # System/virtual mounts excluded
    assert "/" not in paths
    assert "/sys" not in paths
    assert "/tmp" not in paths


def test_detect_drives_sorted_by_free_space(tmp_path):
    fake_mounts = """\
/dev/sda3 /mnt/small ext4 rw 0 0
/dev/sda4 /mnt/large ext4 rw 0 0
"""
    mounts_file = tmp_path / "mounts"
    mounts_file.write_text(fake_mounts)

    def fake_du(path):
        return MagicMock(free=1 * 1024**3 if "small" in path else 100 * 1024**3)

    with patch("scripts.backup.MOUNTS_FILE", str(mounts_file)):
        with patch("scripts.backup.shutil.disk_usage", side_effect=fake_du):
            drives = detect_drives()

    assert drives[0]["path"] == "/mnt/large"


def test_create_backup_calls_tar(tmp_path):
    home_dir = tmp_path / "home" / "user"
    home_dir.mkdir(parents=True)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "tar"
    assert "czf" in cmd[1]
    assert "2026-05-20" in cmd[2]
    assert str(home_dir) in cmd


def test_create_backup_raises_on_tar_failure(tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="No space left")
        with pytest.raises(RuntimeError, match="tar failed"):
            create_backup(str(home_dir), str(tmp_path / "backup"), date_str="2026-05-20")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/organize-home && python -m pytest tests/test_backup.py -v
```

Expected: `ImportError` — `scripts.backup` does not exist yet.

- [ ] **Step 3: Implement scripts/backup.py**

```python
import shutil
import subprocess
from datetime import date
from pathlib import Path

MOUNTS_FILE = "/proc/mounts"

# Mount points to always exclude from drive suggestions
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
            parts = line.split()
            if len(parts) < 3:
                continue
            device, mountpoint, fstype = parts[0], parts[1], parts[2]
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/organize-home && python -m pytest tests/test_backup.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/backup.py tests/test_backup.py
git commit -m "feat: backup.py — drive detection and tar archive creation"
```

---

## Task 4: index_files.py

**Files:**
- Create: `scripts/index_files.py`
- Create: `tests/test_index_files.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index_files.py`:

```python
import json
import stat
import pytest
from pathlib import Path
from scripts.index_files import build_index, save_index, load_index


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "user"
    home.mkdir()
    (home / "Downloads").mkdir()
    (home / "Documents").mkdir()
    (home / "Downloads" / "SubDir").mkdir()
    # Depth-0 files (directly in home)
    (home / "notes.txt").write_text("hello")
    (home / "photo.jpg").write_bytes(b"\xff\xd8\xff")
    # Depth-1 files (in first-level subdir)
    (home / "Downloads" / "archive.zip").write_bytes(b"PK")
    (home / "Documents" / "report.pdf").write_bytes(b"%PDF")
    # Depth-2 files (should NOT be indexed)
    (home / "Downloads" / "SubDir" / "deep.txt").write_text("deep")
    return home


def test_build_index_includes_depth_0(fake_home):
    entries = build_index(str(fake_home))
    paths = [e["path"] for e in entries]
    assert str(fake_home / "notes.txt") in paths
    assert str(fake_home / "photo.jpg") in paths


def test_build_index_includes_depth_1(fake_home):
    entries = build_index(str(fake_home))
    paths = [e["path"] for e in entries]
    assert str(fake_home / "Downloads" / "archive.zip") in paths
    assert str(fake_home / "Documents" / "report.pdf") in paths


def test_build_index_excludes_depth_2(fake_home):
    entries = build_index(str(fake_home))
    paths = [e["path"] for e in entries]
    assert str(fake_home / "Downloads" / "SubDir" / "deep.txt") not in paths


def test_build_index_entry_fields(fake_home):
    entries = build_index(str(fake_home))
    pdf_entry = next(e for e in entries if e["path"].endswith("report.pdf"))
    assert pdf_entry["ext"] == ".pdf"
    assert pdf_entry["size"] > 0
    assert pdf_entry["mtime"] != ""
    assert isinstance(pdf_entry["is_executable"], bool)


def test_build_index_detects_executable(fake_home):
    exe = fake_home / "Downloads" / "installer.run"
    exe.write_bytes(b"\x7fELF")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    entries = build_index(str(fake_home))
    exe_entry = next(e for e in entries if e["path"].endswith("installer.run"))
    assert exe_entry["is_executable"] is True


def test_save_and_load_index(fake_home, tmp_path):
    entries = build_index(str(fake_home))
    index_path = tmp_path / "index.json"
    save_index(entries, str(index_path))
    loaded = load_index(str(index_path))
    assert len(loaded) == len(entries)
    assert loaded[0]["path"] == entries[0]["path"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/organize-home && python -m pytest tests/test_index_files.py -v
```

Expected: `ImportError` — `scripts.index_files` does not exist yet.

- [ ] **Step 3: Implement scripts/index_files.py**

```python
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


def build_index(home_dir: str) -> list[dict]:
    """Walk home_dir and first-level subdirectories. Returns list of file entry dicts.

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/organize-home && python -m pytest tests/test_index_files.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/index_files.py tests/test_index_files.py
git commit -m "feat: index_files.py — two-level home directory walker"
```

---

## Task 5: categorize.py

**Files:**
- Create: `scripts/categorize.py`
- Create: `tests/test_categorize.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_categorize.py`:

```python
import stat
import pytest
from pathlib import Path
from scripts.categorize import get_destination, ARCHIVE_EXTS, EMAIL_EXTS, EBOOK_EXTS, IMAGE_EXTS


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "user"
    (home / "Downloads").mkdir(parents=True)
    (home / "Documents").mkdir()
    (home / "Pictures").mkdir()
    return home


def _entry(path: str, ext: str, is_executable: bool = False):
    return {"path": path, "ext": ext, "is_executable": is_executable}


def test_archive_in_downloads_routes_to_zip_archive(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "data.zip"), ".zip")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Zip Archive")
    assert rule == "archive"


def test_archive_in_home_routes_to_zip_archive(fake_home):
    entry = _entry(str(fake_home / "backup.tar.gz"), ".gz")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Zip Archive")


def test_email_routes_to_emails(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "msg.eml"), ".eml")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Emails")
    assert rule == "email"


def test_epub_routes_to_books(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "book.epub"), ".epub")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Books")
    assert rule == "ebook"


def test_executable_in_downloads_routes_to_execfiles(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "installer.run"), ".run", is_executable=True)
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Downloads" / "ExecFiles")
    assert rule == "executable"


def test_executable_not_in_downloads_not_routed(fake_home):
    entry = _entry(str(fake_home / "myscript.sh"), ".sh", is_executable=True)
    result = get_destination(entry, str(fake_home))
    assert result is None


def test_image_in_downloads_routes_to_pictures(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "photo.jpg"), ".jpg")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Pictures")
    assert rule == "image"


def test_image_in_documents_routes_to_pictures(fake_home):
    entry = _entry(str(fake_home / "Documents" / "scan.png"), ".png")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Pictures")


def test_image_already_in_pictures_not_routed(fake_home):
    entry = _entry(str(fake_home / "Pictures" / "holiday.jpg"), ".jpg")
    result = get_destination(entry, str(fake_home))
    assert result is None


def test_pdf_not_routed_by_rules(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "contract.pdf"), ".pdf")
    result = get_destination(entry, str(fake_home))
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/organize-home && python -m pytest tests/test_categorize.py -v
```

Expected: `ImportError` — `scripts.categorize` does not exist yet.

- [ ] **Step 3: Implement scripts/categorize.py**

```python
import shutil
from pathlib import Path

ARCHIVE_EXTS = {".zip", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tar"}
EMAIL_EXTS = {".eml", ".msg"}
EBOOK_EXTS = {".epub", ".mobi", ".azw3"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}

# Directories from which images are moved to Pictures
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
    """Apply rule-based moves. Skips files already at their destination.

    Returns list of entries that were NOT routed (need AI review).
    """
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/organize-home && python -m pytest tests/test_categorize.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/categorize.py tests/test_categorize.py
git commit -m "feat: categorize.py — rule-based file routing"
```

---

## Task 6: rename_images.py

**Files:**
- Create: `scripts/rename_images.py`
- Create: `tests/test_rename_images.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rename_images.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from scripts.rename_images import is_non_descriptive, get_exif_date, make_unique_stem, scan_for_rename


def test_all_digits_is_non_descriptive():
    assert is_non_descriptive("1000037861") is True


def test_short_name_is_non_descriptive():
    assert is_non_descriptive("abc") is True


def test_camera_pattern_img_is_non_descriptive():
    assert is_non_descriptive("IMG_2034") is True


def test_camera_pattern_dsc_is_non_descriptive():
    assert is_non_descriptive("DSC_0042") is True


def test_camera_pattern_dcim_is_non_descriptive():
    assert is_non_descriptive("DCIM_1234") is True


def test_camera_pattern_pict_is_non_descriptive():
    assert is_non_descriptive("PICT_9876") is True


def test_descriptive_name_not_flagged():
    assert is_non_descriptive("red-barn-winter") is False
    assert is_non_descriptive("family_reunion_2024") is False
    assert is_non_descriptive("graduation_ceremony") is False


def test_get_exif_date_returns_date_string(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "2023:06:15 14:30:00\n"

    with patch("scripts.rename_images.subprocess.run", return_value=mock_result):
        result = get_exif_date(str(img))

    assert result == "2023-06-15"


def test_get_exif_date_returns_none_on_failure(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff")

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    with patch("scripts.rename_images.subprocess.run", return_value=mock_result):
        result = get_exif_date(str(img))

    assert result is None


def test_make_unique_stem_no_collision(tmp_path):
    stem = make_unique_stem(tmp_path, "2023-06-15", ".jpg")
    assert stem == "2023-06-15_001"


def test_make_unique_stem_with_collision(tmp_path):
    (tmp_path / "2023-06-15_001.jpg").write_bytes(b"")
    stem = make_unique_stem(tmp_path, "2023-06-15", ".jpg")
    assert stem == "2023-06-15_002"


def test_scan_for_rename_finds_non_descriptive(tmp_path):
    pictures = tmp_path / "Pictures"
    pictures.mkdir()
    (pictures / "1000037861.jpg").write_bytes(b"\xff\xd8\xff")
    (pictures / "holiday_beach.jpg").write_bytes(b"\xff\xd8\xff")

    results = scan_for_rename(str(pictures))
    paths = [r["path"] for r in results]
    assert str(pictures / "1000037861.jpg") in paths
    assert str(pictures / "holiday_beach.jpg") not in paths
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/organize-home && python -m pytest tests/test_rename_images.py -v
```

Expected: `ImportError` — `scripts.rename_images` does not exist yet.

- [ ] **Step 3: Implement scripts/rename_images.py**

```python
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
    """Return YYYY-MM-DD from EXIF DateTimeOriginal, or None."""
    result = subprocess.run(
        ["exiftool", "-DateTimeOriginal", "-s3", path],
        capture_output=True, text=True
    )
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/organize-home && python -m pytest tests/test_rename_images.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/rename_images.py tests/test_rename_images.py
git commit -m "feat: rename_images.py — EXIF/AI/date image rename chain"
```

---

## Task 7: ai_review.py

**Files:**
- Create: `scripts/ai_review.py`
- Create: `tests/test_ai_review.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ai_review.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.ai_review import extract_first_page, record_result
from scripts.state import StateManager


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "state.json"


def test_extract_pdf_returns_text(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    # Write a minimal real PDF with text (use pypdf to create one)
    from pypdf import PdfWriter
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    # Blank PDF returns empty string, not an error
    result = extract_first_page(str(pdf_path))
    assert isinstance(result, str)


def test_extract_txt_returns_content(tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("This is a legal contract between parties.")
    result = extract_first_page(str(txt))
    assert "legal contract" in result


def test_extract_md_returns_content(tmp_path):
    md = tmp_path / "readme.md"
    md.write_text("# Family Budget\n\nMonthly expenses for the household.")
    result = extract_first_page(str(md))
    assert "Family Budget" in result


def test_extract_unknown_extension_returns_none(tmp_path):
    f = tmp_path / "unknown.xyz123"
    f.write_bytes(b"\x00\x01\x02binary")
    result = extract_first_page(str(f))
    assert result is None


def test_record_result_saves_to_state(tmp_path, state_file):
    sm = StateManager(state_file)
    record_result(
        path="/home/user/Downloads/mystery.pdf",
        result={"category": "Legal", "folder": "/home/user/Legal",
                "confidence": 0.85, "reason": "Contract language"},
        state=sm,
    )
    data = sm.load()
    assert len(data["moves"]) == 0  # record_result doesn't move, just logs intent


def test_record_low_confidence_goes_to_queue(tmp_path, state_file):
    sm = StateManager(state_file)
    record_result(
        path="/home/user/Downloads/mystery.pdf",
        result={"category": "Unknown", "folder": "/home/user/Human Review",
                "confidence": 0.2, "reason": "Cannot determine"},
        state=sm,
    )
    data = sm.load()
    assert len(data["low_confidence"]) == 1
    assert data["low_confidence"][0]["confidence"] == 0.2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/organize-home && python -m pytest tests/test_ai_review.py -v
```

Expected: `ImportError` — `scripts.ai_review` does not exist yet.

- [ ] **Step 3: Implement scripts/ai_review.py**

```python
"""Document first-page text extractor and AI review result recorder.

CLI modes:
  --extract <path>               Print first-page text to stdout (for agent to review)
  --record <path> <json_result>  Record agent's categorization result into state file
"""
import json
import shutil
import sys
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".csv", ".log"}
REVIEWABLE_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".rtf"} | TEXT_EXTENSIONS
MAX_TEXT_CHARS = 3000  # First page approximation for text files


def extract_first_page(path: str) -> str | None:
    """Extract first-page text from a document. Returns None for unsupported types."""
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(path)
    if ext in (".docx", ".doc"):
        return _extract_docx(path)
    if ext in TEXT_EXTENSIONS:
        return _extract_text(path)
    if ext in (".odt", ".rtf"):
        return _extract_raw_fallback(path)
    return None


def _extract_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        if not reader.pages:
            return ""
        return reader.pages[0].extract_text() or ""
    except Exception:
        return ""


def _extract_docx(path: str) -> str:
    try:
        from docx import Document
        doc = Document(path)
        lines = []
        for para in doc.paragraphs[:40]:
            lines.append(para.text)
            if sum(len(l) for l in lines) > MAX_TEXT_CHARS:
                break
        return "\n".join(lines)
    except Exception:
        return ""


def _extract_text(path: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return text[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def _extract_raw_fallback(path: str) -> str:
    try:
        raw = Path(path).read_bytes()
        return raw[:MAX_TEXT_CHARS].decode("utf-8", errors="replace")
    except Exception:
        return ""


def record_result(path: str, result: dict, state) -> None:
    """Record AI categorization result into state.

    High confidence (>0.5): logged as pending move (agent will move the file).
    Low confidence (<=0.5): added to low_confidence queue.
    """
    confidence = result.get("confidence", 0)
    if confidence > 0.5:
        # Agent will perform the actual move; we log intent here
        state.add_move(path, result["folder"], phase=5, rule=f"ai:{result['category']}")
    else:
        state.add_low_confidence(path, result.get("folder", ""), confidence, result.get("reason", ""))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ai_review.py --extract <path> | --record <path> <json>")
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "--extract":
        text = extract_first_page(sys.argv[2])
        if text is None:
            print(json.dumps({"error": "unsupported file type"}))
        else:
            print(json.dumps({"text": text}))
    elif mode == "--record":
        from scripts.state import StateManager
        result = json.loads(sys.argv[3])
        sm = StateManager()
        record_result(sys.argv[2], result, sm)
        print(json.dumps({"ok": True}))
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/organize-home && python -m pytest tests/test_ai_review.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai_review.py tests/test_ai_review.py
git commit -m "feat: ai_review.py — document text extraction and result recording"
```

---

## Task 8: html_report.py

**Files:**
- Create: `scripts/html_report.py`
- Create: `tests/test_html_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_html_report.py`:

```python
import pytest
from pathlib import Path
from scripts.html_report import generate_report


@pytest.fixture
def sample_state():
    return {
        "version": 1,
        "started_at": "2026-05-20T10:00:00+00:00",
        "backup_path": "/mnt/data/home-backup-2026-05-20.tar.gz",
        "vision": True,
        "completed_phases": [0, 1, 2, 3, 4, 5, 6],
        "moves": [
            {"from": "/home/user/Downloads/archive.zip",
             "to": "/home/user/Zip Archive/archive.zip",
             "phase": 3, "rule": "archive"},
            {"from": "/home/user/Downloads/contract.pdf",
             "to": "/home/user/Legal/contract.pdf",
             "phase": 5, "rule": "ai:Legal"},
        ],
        "low_confidence": [
            {"path": "/home/user/Downloads/mystery.pdf",
             "proposed": "/home/user/Human Review",
             "confidence": 0.3,
             "reason": "Unable to determine document purpose"},
        ],
        "errors": [],
    }


def test_generate_report_creates_file(tmp_path, sample_state):
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    assert output.exists()


def test_report_contains_summary_stats(tmp_path, sample_state):
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    assert "2026-05-20" in html
    assert "2 files moved" in html or "2 moves" in html


def test_report_contains_move_log(tmp_path, sample_state):
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    assert "archive.zip" in html
    assert "Zip Archive" in html
    assert "contract.pdf" in html


def test_report_contains_amber_section(tmp_path, sample_state):
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    assert "mystery.pdf" in html
    assert "Needs Your Input" in html or "amber" in html.lower()
    assert "0.3" in html or "30%" in html


def test_report_contains_file_links(tmp_path, sample_state):
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    assert "file://" in html


def test_report_no_amber_section_when_queue_empty(tmp_path, sample_state):
    sample_state["low_confidence"] = []
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    assert "mystery.pdf" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/organize-home && python -m pytest tests/test_html_report.py -v
```

Expected: `ImportError` — `scripts.html_report` does not exist yet.

- [ ] **Step 3: Implement scripts/html_report.py**

```python
"""HTML report generator.

CLI: html_report.py --state <state_json_path> --home <home_dir> --output <html_path>
"""
import json
import sys
from datetime import datetime
from pathlib import Path

CSS = """
body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 2rem; color: #333; }
h1 { color: #1a1a2e; } h2 { color: #16213e; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }
.stats { display: flex; gap: 2rem; background: #f8f9fa; padding: 1rem; border-radius: 8px; margin: 1rem 0; }
.stat { text-align: center; } .stat .num { font-size: 2rem; font-weight: bold; color: #0f3460; }
.stat .label { font-size: 0.85rem; color: #666; }
details summary { cursor: pointer; font-weight: bold; padding: 0.5rem; background: #f0f0f0; border-radius: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { background: #16213e; color: white; padding: 0.5rem; text-align: left; }
td { padding: 0.4rem 0.5rem; border-bottom: 1px solid #eee; }
tr:hover { background: #f8f9fa; }
.amber { background: #fff8e1; border: 2px solid #ffc107; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; }
.amber h2 { color: #856404; border-color: #ffc107; }
.confidence { font-weight: bold; color: #856404; }
.cmd { font-family: monospace; background: #f4f4f4; padding: 0.2rem 0.5rem; border-radius: 3px;
       border: 1px solid #ddd; cursor: pointer; }
.human-review { background: #fff3f3; border: 2px solid #dc3545; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; }
a { color: #0f3460; } a:hover { color: #e94560; }
"""


def generate_report(state: dict, home_dir: str, output_path: str) -> None:
    moves = state.get("moves", [])
    low_conf = state.get("low_confidence", [])
    errors = state.get("errors", [])
    backup_path = state.get("backup_path", "unknown")
    started_at = state.get("started_at", "")
    date_str = started_at[:10] if started_at else datetime.now().strftime("%Y-%m-%d")

    human_review_entries = [
        m for m in moves
        if "Human Review" in m.get("to", "")
    ]
    auto_moved = [m for m in moves if m not in human_review_entries]

    sections = []

    # Stats bar
    sections.append(f"""
<div class="stats">
  <div class="stat"><div class="num">{len(moves)}</div><div class="label">files moved</div></div>
  <div class="stat"><div class="num">{len(low_conf)}</div><div class="label">needs review</div></div>
  <div class="stat"><div class="num">{len(human_review_entries)}</div><div class="label">human review</div></div>
  <div class="stat"><div class="num">{len(errors)}</div><div class="label">errors</div></div>
</div>
<p><strong>Backup:</strong> <code>{backup_path}</code><br>
<strong>Run date:</strong> {date_str}</p>
""")

    # Amber section — low confidence
    if low_conf:
        rows = ""
        for lc in low_conf:
            conf_pct = f"{lc['confidence']*100:.0f}%"
            mv_cmd = f"mv '{lc['path']}' '{lc['proposed']}'"
            rows += f"""
<tr>
  <td><a href="file://{lc['path']}">{Path(lc['path']).name}</a></td>
  <td><code>{lc['path']}</code></td>
  <td><code>{lc['proposed']}</code></td>
  <td class="confidence">{conf_pct}</td>
  <td>{lc['reason']}</td>
  <td><span class="cmd" onclick="navigator.clipboard.writeText(this.dataset.cmd)" data-cmd="{mv_cmd}">📋 copy</span></td>
</tr>"""
        sections.append(f"""
<div class="amber">
<h2>⚠️ Needs Your Input ({len(low_conf)} files)</h2>
<p>These files have a confidence score below 50%. Tell the agent which moves to make,
correct any proposals, or say <strong>"move all proposed"</strong> to accept them all.</p>
<table>
<tr><th>File</th><th>Current Location</th><th>Proposed Destination</th>
    <th>Confidence</th><th>Reason</th><th>Command</th></tr>
{rows}
</table>
</div>""")

    # Human Review section
    if human_review_entries:
        rows = "".join(
            f'<tr><td><a href="file://{m["from"]}">{Path(m["from"]).name}</a></td>'
            f'<td><code>{m["from"]}</code></td></tr>'
            for m in human_review_entries
        )
        sections.append(f"""
<div class="human-review">
<h2>🔍 Human Review ({len(human_review_entries)} files)</h2>
<p>The AI could not categorize these files. Please review them manually.</p>
<table><tr><th>File</th><th>Original Location</th></tr>{rows}</table>
</div>""")

    # Move log
    if auto_moved:
        rows = "".join(
            f'<tr><td><a href="file://{m["to"]}">{Path(m["from"]).name}</a></td>'
            f'<td><code>{m["from"]}</code></td>'
            f'<td><code>{m["to"]}</code></td>'
            f'<td>{m.get("rule","")}</td></tr>'
            for m in auto_moved
        )
        sections.append(f"""
<details open>
<summary>Run Log ({len(auto_moved)} moves)</summary>
<table>
<tr><th>File</th><th>From</th><th>To</th><th>Rule</th></tr>
{rows}
</table>
</details>""")

    # Directory tree
    sections.append(_build_dir_tree(home_dir))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Home Directory Index — {date_str}</title>
<style>{CSS}</style>
</head>
<body>
<h1>Home Directory Index</h1>
{"".join(sections)}
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _build_dir_tree(home_dir: str) -> str:
    home = Path(home_dir)
    items = ["<h2>Directory Tree</h2><ul>"]
    for item in sorted(home.iterdir()):
        if item.is_dir():
            items.append(f'<li>📁 <strong>{item.name}/</strong><ul>')
            for child in sorted(item.iterdir()):
                if child.is_file():
                    items.append(
                        f'<li><a href="file://{child}">📄 {child.name}</a></li>'
                    )
            items.append("</ul></li>")
        elif item.is_file():
            items.append(f'<li><a href="file://{item}">📄 {item.name}</a></li>')
    items.append("</ul>")
    return "\n".join(items)


if __name__ == "__main__":
    import argparse
    from scripts.state import StateManager
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    sm = StateManager(args.state)
    generate_report(sm.load(), args.home, args.output)
    print(f"Report written to {args.output}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/organize-home && python -m pytest tests/test_html_report.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd /home/user/organize-home && python -m pytest -v
```

Expected: all tests PASS (35+ tests across all modules).

- [ ] **Step 6: Commit**

```bash
git add scripts/html_report.py tests/test_html_report.py
git commit -m "feat: html_report.py — browsable HTML index with amber review section"
```

---

## Task 9: references/rules.md

**Files:**
- Create: `references/rules.md`

- [ ] **Step 1: Create the categorization rules reference**

Create `references/rules.md`:

```markdown
# organize-home Categorization Rules

This file is loaded by the agent during Phase 5 (AI document review) to guide
consistent categorization decisions.

## Rule-Based Moves (Phase 3 — no AI needed)

| Extension(s) | Destination |
|---|---|
| .zip .gz .bz2 .xz .7z .rar .tar | ~/Zip Archive/ |
| .eml .msg | ~/Emails/ |
| .epub .mobi .azw3 | ~/Books/ |
| Executable in Downloads/ | ~/Downloads/ExecFiles/ |
| .jpg .jpeg .png .gif .webp .heic (in home, Documents, Downloads) | ~/Pictures/ |

## AI Document Categorization (Phase 5)

When reviewing a document, assign it to the MOST SPECIFIC existing folder if one
fits well. If no existing folder fits, create a new descriptive first-level folder.

### Preferred Existing Folders (match before creating new)

- `~/Documents/` — generic documents with no better home
- `~/Practice Files/` — anything related to expatlaw.info, international law practice, client matters
- `~/Financial/` — bank statements, tax records, invoices, financial reports
- `~/HamRadio/` — amateur radio, ARRL, frequencies, callsigns, equipment
- `~/Career/` — resumes, job applications, professional development
- `~/Genealogy/` — family history, ancestry, birth/death records
- `~/Travel/` — itineraries, bookings, travel documents
- `~/Personal Records/` — medical, insurance, identification documents
- `~/Academic/` — coursework, research, educational materials
- `~/Books/` — ebooks (handled in Phase 3), also PDFs of books/manuals
- `~/Pictures/` — images (handled in Phase 3)

### Folder Naming Guidelines

- Match existing folder names exactly when close enough
  - e.g., "Practice Files" NOT "Expat Law" if the former already exists
- Create new folders for genuinely new categories:
  - `~/Family/` — personal family matters, household records
  - `~/Contracts/` — if many legal contracts outside law practice
  - `~/Medical/` — if separate from Personal Records makes sense
- Name folders by topic, not by file type
  - GOOD: `~/Legal Filings/`, `~/Tax Records/`
  - BAD: `~/PDFs/`, `~/WordDocs/`

### Confidence Scoring Guidelines

- **0.8–1.0** — First page clearly identifies the document type and subject
- **0.5–0.8** — Reasonable inference but some ambiguity (multiple plausible folders)
- **0.3–0.5** — Significant uncertainty; route to low-confidence queue
- **0.0–0.3** — Cannot determine; route to ~/Human Review/

### Special Cases

- Legal filings with case numbers/court names → `~/Practice Files/` or `~/Legal Filings/`
- Bank statements → `~/Financial/`
- Password files, credentials → `~/Personal Records/` (flag to user)
- Code/scripts not in a project folder → `~/Coding Projects/` if exists
- Empty or near-empty documents → confidence 0.1, route to Human Review
```

- [ ] **Step 2: Commit**

```bash
git add references/rules.md
git commit -m "docs: categorization rules reference for AI document review"
```

---

## Task 10: claude/SKILL.md

**Files:**
- Create: `claude/SKILL.md`

- [ ] **Step 1: Create Claude Code skill**

Create `claude/SKILL.md`:

```markdown
---
name: organize-home
description: Organizes the user's home directory by backing it up, sorting files by type, using AI to categorize documents, renaming unnamed images, and generating a browsable HTML index. Use when the user says "organize my home", "clean up my files", "sort my downloads", or similar.
version: 1.0.0
---

# organize-home

Organizes ~/home by backing up, sorting files into typed folders, and producing an HTML index.
Scripts live at `~/organize-home/scripts/`. State file: `~/.organize-home-state.json`.

## Required binaries
Before starting, verify these are installed: `tar`, `file`, `exiftool`.
If any are missing, print install instructions and stop:
- exiftool: `sudo pacman -S perl-image-exiftool` (Arch) or `sudo apt install libimage-exiftool-perl`
- tar, file: pre-installed on Linux

Verify Python packages: `python3 -c "import pypdf, docx, PIL"`. If missing:
`pip install pypdf python-docx Pillow`

## Vision capability test
Before Phase 4, test whether you can describe images:
1. Create a 1×1 white PNG: `python3 -c "from PIL import Image; img=Image.new('RGB',(1,1),(255,255,255)); img.save('/tmp/vision_test.png')"`
2. Attempt to describe `/tmp/vision_test.png`
3. If you can describe it (e.g. "a white pixel"), set vision=true in state; otherwise set vision=false.
Run: `python3 ~/organize-home/scripts/state.py` is handled via the StateManager in scripts.

## Resume check
At the start of every run, check `~/.organize-home-state.json`. If it exists, read
`completed_phases` and skip those phases. Tell the user: "Resuming from phase N."

---

## Phase 0: Preflight

1. Run dep checks above.
2. Detect drives: `python3 -c "import sys; sys.path.insert(0,'~/organize-home'); from scripts.backup import detect_drives; import json; print(json.dumps(detect_drives(), indent=2))"`
3. Present drive options to user (ranked by free space). Include `/tmp/home-backup-YYYYMMDD` as last-resort option with warning: "This will be deleted on reboot."
4. Ask user to confirm backup destination.
5. Run vision test and record result in state.
6. Mark phase 0 complete.

## Phase 1: Backup

```bash
python3 ~/organize-home/scripts/backup.py  # or invoke via Python
```

Run via Python:
```python
import sys; sys.path.insert(0, str(Path.home() / 'organize-home'))
from scripts.backup import create_backup
result = create_backup(str(Path.home()), CONFIRMED_BACKUP_DIR)
```
Record backup path in state. If it fails, abort the entire run.
Mark phase 1 complete.

## Phase 2: Index

```bash
python3 -c "
import sys; sys.path.insert(0, '$(echo ~)/organize-home')
from scripts.index_files import build_index, save_index
entries = build_index('$(echo ~)')
save_index(entries, '$(echo ~)/.organize-home-index.json')
print(f'Indexed {len(entries)} files')
"
```
Mark phase 2 complete.

## Phase 3: Rule-based moves

```bash
python3 -c "
import sys, json; sys.path.insert(0, '$(echo ~)/organize-home')
from scripts.index_files import load_index
from scripts.categorize import apply_moves
from scripts.state import StateManager
sm = StateManager()
entries = load_index('$(echo ~)/.organize-home-index.json')
unrouted = apply_moves(entries, '$(echo ~)', sm)
print(f'Moved {len(entries)-len(unrouted)} files. {len(unrouted)} need AI review.')
with open('/tmp/unrouted.json','w') as f: json.dump(unrouted, f)
"
```
Mark phase 3 complete.

## Phase 4: Image rename

```bash
python3 ~/organize-home/scripts/rename_images.py --scan ~/Pictures
```
This prints a JSON list of images needing rename, each with `path` and `exif_date`.

For each image in the list:
- If `exif_date` is not null: run `python3 ~/organize-home/scripts/rename_images.py --rename "<path>" "<exif_date>"`
- If `exif_date` is null AND vision=true in state: view the image, create a 6-word-max slug, run `--rename "<path>" "<slug>"`
- If `exif_date` is null AND vision=false: get mtime date via `python3 -c "from scripts.rename_images import get_mtime_date; print(get_mtime_date('<path>'))"` then run `--rename`

Mark phase 4 complete.

## Phase 5: AI document review

Load `references/rules.md` now for guidance.

For each file in `/tmp/unrouted.json` with extension in `.pdf .doc .docx .txt .md .odt .rtf`:

```bash
python3 ~/organize-home/scripts/ai_review.py --extract "/path/to/file"
```

Review the extracted text. Return your assessment as JSON:
```json
{"category": "Legal", "folder": "/home/user/Legal", "confidence": 0.85, "reason": "Contract language with case number"}
```

Then record the result:
```bash
python3 ~/organize-home/scripts/ai_review.py --record "/path/to/file" '{"category":"Legal","folder":"/home/user/Legal","confidence":0.85,"reason":"..."}'
```

If confidence > 0.5: move the file now with `shutil.move` or `mv`.
If confidence ≤ 0.5: do NOT move the file. It is queued in the state file.

Mark phase 5 complete.

## Phase 6: HTML report

```bash
python3 ~/organize-home/scripts/html_report.py \
  --state ~/.organize-home-state.json \
  --home ~ \
  --output ~/home-index.html
```
Mark phase 6 complete.

## Phase 7: Clarification (if needed)

Check `~/.organize-home-state.json` for `low_confidence` entries.
If the list is non-empty:

Tell the user:
> "I've organized everything I'm confident about. Open file:///home/YOUR_USER/home-index.html — the amber section lists [N] files I'm uncertain about, with my proposed destinations. Tell me which moves to make, correct any proposals, or say 'move all proposed' to accept them all."

Wait for user response. Apply moves as directed. For each resolved file, remove it from the low_confidence list in the state file.

## Phase 8: Final report

Re-run the HTML report command from Phase 6.
Delete `~/.organize-home-state.json` (clean completion).
Tell the user: "Done. Your home directory has been organized. Open file:///home/YOUR_USER/home-index.html to browse the result."
```

- [ ] **Step 2: Commit**

```bash
git add claude/SKILL.md
git commit -m "feat: claude/SKILL.md — Claude Code platform skill"
```

---

## Task 11: openclaw/SKILL.md

**Files:**
- Create: `openclaw/SKILL.md`

- [ ] **Step 1: Create OpenClaw skill**

Create `openclaw/SKILL.md`:

```markdown
---
name: organize-home
description: Organizes the user's home directory by backing it up, sorting files by type, using AI to categorize documents, renaming unnamed images, and generating a browsable HTML index. Use when the user says "organize my home", "clean up my files", or "sort my downloads".
metadata:
  openclaw:
    os: ["linux"]
    requires:
      bins: [tar, file, exiftool, python3]
---

# organize-home

Organizes ~/home by backing up, sorting files into typed folders, and producing an HTML index.
Scripts live at `~/organize-home/scripts/`. State file: `~/.organize-home-state.json`.

## Required Python packages
Verify: `python3 -c "import pypdf, docx, PIL"`. If missing:
`pip install pypdf python-docx Pillow`

## Vision capability self-test
Before Phase 4, test whether you have image description capability:
1. `python3 -c "from PIL import Image; img=Image.new('RGB',(1,1),(255,255,255)); img.save('/tmp/vision_test.png')"`
2. Attempt to describe the image at `/tmp/vision_test.png`
3. If you receive a meaningful description (e.g. "a single white pixel"), you have vision capability.
   Record `vision: true` in state. Otherwise record `vision: false`.
   All image AI-description steps depend on this flag — fall back to EXIF/date if false.

## Resume check
At the start of every run, check `~/.organize-home-state.json`. If it exists, read
`completed_phases` and skip those phases. Tell the user: "Resuming from phase N."

---

## Phase 0: Preflight

1. Verify binaries (`tar`, `file`, `exiftool`) and Python packages.
2. Detect drives:
```bash
python3 -c "
import sys; sys.path.insert(0,'$(echo ~)/organize-home')
from scripts.backup import detect_drives; import json; print(json.dumps(detect_drives(),indent=2))
"
```
3. Present options (ranked by free space). Include `/tmp/home-backup-YYYYMMDD` as last resort with warning it is deleted on reboot.
4. Ask user to confirm backup destination before proceeding.
5. Run vision self-test and record result.
6. Mark phase 0 complete.

## Phase 1: Backup

```python
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / 'organize-home'))
from scripts.backup import create_backup
result = create_backup(str(__import__('pathlib').Path.home()), CONFIRMED_BACKUP_DIR)
```
Record backup path in state. Abort entire run if backup fails.
Mark phase 1 complete.

## Phase 2: Index

```bash
python3 -c "
import sys; sys.path.insert(0,'$(echo ~)/organize-home')
from scripts.index_files import build_index, save_index
entries = build_index('$(echo ~)')
save_index(entries, '$(echo ~)/.organize-home-index.json')
print(f'Indexed {len(entries)} files')
"
```
Mark phase 2 complete.

## Phase 3: Rule-based moves

```bash
python3 -c "
import sys, json; sys.path.insert(0,'$(echo ~)/organize-home')
from scripts.index_files import load_index
from scripts.categorize import apply_moves
from scripts.state import StateManager
sm = StateManager()
entries = load_index('$(echo ~)/.organize-home-index.json')
unrouted = apply_moves(entries, '$(echo ~)', sm)
print(f'Moved {len(entries)-len(unrouted)} files. {len(unrouted)} need AI review.')
with open('/tmp/unrouted.json','w') as f: json.dump(unrouted, f)
"
```
Mark phase 3 complete.

## Phase 4: Image rename

```bash
python3 ~/organize-home/scripts/rename_images.py --scan ~/Pictures
```
For each result:
- If `exif_date` present: `python3 ~/organize-home/scripts/rename_images.py --rename "<path>" "<exif_date>"`
- If `exif_date` null AND vision=true: describe the image, then `--rename "<path>" "<your-slug>"`
- If `exif_date` null AND vision=false: use mtime date, then `--rename`

Mark phase 4 complete.

## Phase 5: AI document review

Load `references/rules.md` now for guidance on categorization decisions.

For each file in `/tmp/unrouted.json` with extension `.pdf .doc .docx .txt .md .odt .rtf`:

```bash
python3 ~/organize-home/scripts/ai_review.py --extract "/path/to/file"
```

Review the text. Decide: `{"category":"...", "folder":"/home/user/Folder", "confidence":0.0–1.0, "reason":"..."}`.
Confidence > 0.5 → move the file immediately, record with `--record`.
Confidence ≤ 0.5 → record only (file stays put, queued for clarification).

Mark phase 5 complete.

## Phase 6: HTML report

```bash
python3 ~/organize-home/scripts/html_report.py \
  --state ~/.organize-home-state.json \
  --home ~ \
  --output ~/home-index.html
```
Mark phase 6 complete.

## Phase 7: Clarification

If `low_confidence` in state is non-empty:
> "I've organized everything I'm confident about. Open file:///home/YOUR_USER/home-index.html — the amber section lists [N] files I'm uncertain about. Tell me which moves to make, correct proposals, or say 'move all proposed'."

Wait for user input. Apply moves. Update state.

## Phase 8: Final report

Re-run Phase 6 HTML command. Delete `~/.organize-home-state.json`.
Tell user: "Done. Browse your new home layout at file:///home/YOUR_USER/home-index.html"
```

- [ ] **Step 2: Commit**

```bash
git add openclaw/SKILL.md
git commit -m "feat: openclaw/SKILL.md — OpenClaw platform skill with requires.bins metadata"
```

---

## Task 12: hermes/SKILL.md

**Files:**
- Create: `hermes/SKILL.md`

- [ ] **Step 1: Create Hermes skill**

Create `hermes/SKILL.md`:

```markdown
---
name: organize-home
description: Organizes the user's home directory by backing it up, sorting files by type, using AI to categorize documents, renaming unnamed images, and generating a browsable HTML index. Use when the user says "organize my home", "clean up my files", or "sort my downloads".
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [files, organization, home, cleanup]
    category: files
    requires_toolsets: [terminal]
    fallback_for_toolsets: [vision]
    config:
      - key: organize_home.default_backup_path
        description: "Default backup destination path (e.g. /mnt/data)"
        default: ""
        prompt: "Where should home backups be stored by default? (leave blank to always ask)"
---

# organize-home

Organizes ~/home by backing up, sorting files into typed folders, and producing an HTML index.
Scripts live at `~/organize-home/scripts/`. State file: `~/.organize-home-state.json`.

## Vision capability
This skill uses `fallback_for_toolsets: [vision]` — if your model does not have vision
capability, image AI-description steps are automatically skipped and EXIF/date naming
is used instead. At runtime, also run a self-test to confirm:
1. `python3 -c "from PIL import Image; img=Image.new('RGB',(1,1),(255,255,255)); img.save('/tmp/vision_test.png')"`
2. Attempt to describe `/tmp/vision_test.png`. If you can, record `vision: true` in state.
   If not (error or no capability), record `vision: false`.

## Config
If `organize_home.default_backup_path` is set in your config, pre-select it as the
default in Phase 0 but still confirm with the user before proceeding.

## Resume check
At the start of every run, check `~/.organize-home-state.json`. If it exists, read
`completed_phases` and skip those phases. Tell the user: "Resuming from phase N."

---

## Phase 0: Preflight

1. Verify: `tar`, `file`, `exiftool` are on PATH. Verify Python packages `pypdf`, `docx`, `PIL`.
2. Detect drives:
```bash
python3 -c "
import sys; sys.path.insert(0,'$(echo ~)/organize-home')
from scripts.backup import detect_drives; import json; print(json.dumps(detect_drives(),indent=2))
"
```
3. If `organize_home.default_backup_path` is configured, show it as the recommended option.
   Always present alternatives and confirm with user. Warn that `/tmp` is cleared on reboot.
4. Run vision self-test. Record result in state.
5. Mark phase 0 complete.

## Phase 1: Backup

```python
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / 'organize-home'))
from scripts.backup import create_backup
result = create_backup(str(__import__('pathlib').Path.home()), CONFIRMED_BACKUP_DIR)
```
Record backup path in state. Abort if backup fails.
Mark phase 1 complete.

## Phase 2: Index

```bash
python3 -c "
import sys; sys.path.insert(0,'$(echo ~)/organize-home')
from scripts.index_files import build_index, save_index
entries = build_index('$(echo ~)')
save_index(entries, '$(echo ~)/.organize-home-index.json')
print(f'Indexed {len(entries)} files')
"
```
Mark phase 2 complete.

## Phase 3: Rule-based moves

```bash
python3 -c "
import sys, json; sys.path.insert(0,'$(echo ~)/organize-home')
from scripts.index_files import load_index
from scripts.categorize import apply_moves
from scripts.state import StateManager
sm = StateManager()
entries = load_index('$(echo ~)/.organize-home-index.json')
unrouted = apply_moves(entries, '$(echo ~)', sm)
print(f'Moved {len(entries)-len(unrouted)} files. {len(unrouted)} need AI review.')
with open('/tmp/unrouted.json','w') as f: json.dump(unrouted, f)
"
```
Mark phase 3 complete.

## Phase 4: Image rename

```bash
python3 ~/organize-home/scripts/rename_images.py --scan ~/Pictures
```
For each result:
- If `exif_date` present: rename using exif date
- If `exif_date` null AND vision=true: describe image and use a slug
- If `exif_date` null AND vision=false: use mtime date

All renames: `python3 ~/organize-home/scripts/rename_images.py --rename "<path>" "<stem>"`
Mark phase 4 complete.

## Phase 5: AI document review

Load `references/rules.md` now for categorization guidance.

For each file in `/tmp/unrouted.json` with extension `.pdf .doc .docx .txt .md .odt .rtf`:
1. `python3 ~/organize-home/scripts/ai_review.py --extract "/path/to/file"` → get text
2. Review text, decide: `{"category":"...", "folder":"...", "confidence":0.0–1.0, "reason":"..."}`
3. `python3 ~/organize-home/scripts/ai_review.py --record "/path/to/file" '<json>'`
4. confidence > 0.5 → move file immediately; ≤ 0.5 → leave for clarification

Mark phase 5 complete.

## Phase 6: HTML report

```bash
python3 ~/organize-home/scripts/html_report.py \
  --state ~/.organize-home-state.json \
  --home ~ \
  --output ~/home-index.html
```
Mark phase 6 complete.

## Phase 7: Clarification

If `low_confidence` is non-empty in state:
> "Open file:///home/YOUR_USER/home-index.html — the amber section lists [N] uncertain files.
> Tell me which moves to make, correct proposals, or say 'move all proposed'."

Apply user instructions. Update state.

## Phase 8: Final report

Re-run Phase 6. Delete `~/.organize-home-state.json`.
Tell user: "Done. Browse your organized home at file:///home/YOUR_USER/home-index.html"
```

- [ ] **Step 2: Commit**

```bash
git add hermes/SKILL.md
git commit -m "feat: hermes/SKILL.md — Hermes platform skill with fallback_for_toolsets"
```

---

## Task 13: Integration Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_integration.py`:

```python
"""End-to-end integration test using a fake home directory."""
import json
import shutil
import stat
import pytest
from pathlib import Path
from scripts.state import StateManager
from scripts.index_files import build_index, save_index, load_index
from scripts.categorize import apply_moves
from scripts.rename_images import scan_for_rename
from scripts.ai_review import extract_first_page, record_result
from scripts.html_report import generate_report


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "user"
    (home / "Downloads").mkdir(parents=True)
    (home / "Documents").mkdir()
    (home / "Pictures").mkdir()

    # Archives
    (home / "Downloads" / "data.zip").write_bytes(b"PK\x03\x04")
    (home / "backup.tar.gz").write_bytes(b"\x1f\x8b")

    # Emails
    (home / "Downloads" / "newsletter.eml").write_text("From: news@test.com\nSubject: Hi")

    # Ebook
    (home / "Downloads" / "guide.epub").write_bytes(b"PK\x03\x04")

    # Executable in Downloads
    exe = home / "Downloads" / "installer.sh"
    exe.write_text("#!/bin/bash\necho hi")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    # Images
    (home / "Downloads" / "IMG_1234.jpg").write_bytes(b"\xff\xd8\xff")
    (home / "Documents" / "scan.png").write_bytes(b"\x89PNG")

    # PDF for AI review
    (home / "Downloads" / "contract.txt").write_text(
        "LEGAL AGREEMENT\nThis agreement is between Party A and Party B..."
    )

    return home


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "state.json"


def test_full_pipeline(fake_home, state_file, tmp_path):
    sm = StateManager(state_file)

    # Phase 2: Index
    entries = build_index(str(fake_home))
    index_path = tmp_path / "index.json"
    save_index(entries, str(index_path))
    loaded = load_index(str(index_path))
    assert len(loaded) > 0

    # Phase 3: Categorize
    unrouted = apply_moves(loaded, str(fake_home), sm)

    # Archives moved
    assert (fake_home / "Zip Archive" / "data.zip").exists()
    assert (fake_home / "Zip Archive" / "backup.tar.gz").exists()

    # Email moved
    assert (fake_home / "Emails" / "newsletter.eml").exists()

    # Ebook moved
    assert (fake_home / "Books" / "guide.epub").exists()

    # Executable moved
    assert (fake_home / "Downloads" / "ExecFiles" / "installer.sh").exists()

    # Images moved to Pictures
    assert (fake_home / "Pictures" / "IMG_1234.jpg").exists()
    assert (fake_home / "Pictures" / "scan.png").exists()

    # State has moves recorded
    data = sm.load()
    assert len(data["moves"]) >= 6

    # Phase 5: AI review (simulate)
    txt_entry = next(e for e in unrouted if e["path"].endswith("contract.txt"))
    text = extract_first_page(txt_entry["path"])
    assert "LEGAL AGREEMENT" in text

    record_result(
        txt_entry["path"],
        {"category": "Legal", "folder": str(fake_home / "Legal"),
         "confidence": 0.9, "reason": "Legal contract language"},
        sm
    )
    data = sm.load()
    legal_moves = [m for m in data["moves"] if "Legal" in m.get("rule", "")]
    assert len(legal_moves) == 1

    # Phase 6: HTML report
    output_html = tmp_path / "home-index.html"
    generate_report(sm.load(), str(fake_home), str(output_html))
    html = output_html.read_text()
    assert output_html.exists()
    assert "file://" in html
    assert "Zip Archive" in html
```

- [ ] **Step 2: Run integration test**

```bash
cd /home/user/organize-home && python -m pytest tests/test_integration.py -v
```

Expected: test PASSES.

- [ ] **Step 3: Run full test suite one final time**

```bash
cd /home/user/organize-home && python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration test covering phases 2–6"
```

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Covered By |
|---|---|
| Backup to user-confirmed path | Task 3 (backup.py), claude/openclaw/hermes SKILL.md Phase 0–1 |
| Drive detection with free space ranking | Task 3 detect_drives() |
| /tmp fallback with reboot warning | All SKILL.md Phase 0 instructions |
| Index first-level subdirs only (no recursion) | Task 4 (index_files.py), test_build_index_excludes_depth_2 |
| Rule-based moves: archives, emails, epubs, executables, images | Task 5 (categorize.py) |
| Image non-descriptive name detection | Task 6 is_non_descriptive() |
| EXIF → AI → mtime rename chain | Task 6 (rename_images.py), SKILL.md Phase 4 |
| Vision capability self-test + fallback | All SKILL.md vision sections; Hermes fallback_for_toolsets |
| AI document review with confidence scoring | Task 7 (ai_review.py), SKILL.md Phase 5 |
| Confidence >0.5 auto-move, ≤0.5 queue | task 7 record_result(), SKILL.md Phase 5 |
| New first-level folders created as needed | categorize.py apply_moves mkdir, SKILL.md Phase 5 |
| Human Review folder for unclassifiable | SKILL.md Phase 5 + html_report.py |
| HTML report with file:// links | Task 8 (html_report.py) |
| Amber section for low-confidence | Task 8 test_report_contains_amber_section |
| Clarification pause with HTML reference | All SKILL.md Phase 7 |
| Resumable via state file | Task 2 (state.py), all SKILL.md resume check |
| Three platform SKILL.md variants | Tasks 10, 11, 12 |
| OpenClaw requires.bins metadata | Task 11 |
| Hermes fallback_for_toolsets: [vision] | Task 12 |
| Hermes config key for default backup path | Task 12 |
| Categorization rules reference | Task 9 (references/rules.md) |

All requirements covered. No gaps found.
