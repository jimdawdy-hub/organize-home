import json
import stat
import pytest
from pathlib import Path
from scripts.index_files import build_index, save_index, load_index


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "jim"
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
