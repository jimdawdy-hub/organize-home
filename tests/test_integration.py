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

    # Text file for AI review
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
