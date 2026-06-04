import os
import stat
import pytest
from pathlib import Path
from scripts.categorize import (
    get_destination, apply_moves,
    ARCHIVE_EXTS, EMAIL_EXTS, EBOOK_EXTS, IMAGE_EXTS,
)
from scripts.state import StateManager


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


def test_pdf_without_litigation_terms_not_routed(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "contract.pdf"), ".pdf")
    result = get_destination(entry, str(fake_home))
    assert result is None


def test_download_filename_bank_statement_routes_to_financial(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "063025 bank statement.pdf"), ".pdf")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Financial")
    assert rule == "financial:bank statement"


def test_download_filename_litigation_terms_route_to_legal_filings(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "Ct Order 4-17-26 (entered).pdf"), ".pdf")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Legal Filings")
    assert rule == "legal:litigation filename"


def test_download_filename_dmr_routes_to_hamradio(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "DMR jhd eng3.data"), ".data")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "HamRadio")
    assert rule == "hamradio:dmr"


def test_download_filename_letter_routes_to_correspondence(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "draft letter to client.docx"), ".docx")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Correspondence")
    assert rule == "correspondence:letter"


def test_download_filename_resume_cv_routes_to_career(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "resume_example_cv.docx"), ".docx")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Career")
    assert rule == "career:resume cv"


def test_download_filename_personal_notes_is_not_auto_routed(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "family notes.pdf"), ".pdf")
    result = get_destination(entry, str(fake_home))
    assert result is None


def test_download_filename_case_citation_routes_to_legal_reference(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "Smith v. Jones 2017 Ill. App..pdf"), ".pdf")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Legal Reference")
    assert rule == "legal_reference:case citation"


def test_download_filename_medical_routes_to_medical_files(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "Med Recs-bills Ortho Surgery Specialists.pdf"), ".pdf")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Medical Files")
    assert rule == "medical:work filename"


def test_download_filename_transcript_routes_to_medical_files(fake_home):
    entry = _entry(str(fake_home / "Downloads" / "Transcript Request of Dr. Troy Boffeli.doc"), ".doc")
    dest, rule = get_destination(entry, str(fake_home))
    assert dest == str(fake_home / "Medical Files")
    assert rule == "medical:work filename"


# ---------- apply_moves safety integration ----------

def _make_file(path: Path, content: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_apply_moves_atomically_avoids_name_collision(fake_home, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    # Pre-existing file in Zip Archive
    (fake_home / "Zip Archive").mkdir()
    (fake_home / "Zip Archive" / "data.zip").write_bytes(b"existing")

    # New file with same name in Downloads
    src = _make_file(fake_home / "Downloads" / "data.zip", b"new content")

    apply_moves(
        [{"path": str(src), "ext": ".zip", "is_executable": False}],
        str(fake_home), sm,
    )

    assert (fake_home / "Zip Archive" / "data.zip").read_bytes() == b"existing"
    assert (fake_home / "Zip Archive" / "data_1.zip").read_bytes() == b"new content"
    assert not src.exists()


def test_apply_moves_refuses_symlink_source_outside_home(fake_home, tmp_path):
    sm = StateManager(tmp_path / "state.json")
    outside = tmp_path / "outside_secret.zip"
    outside.write_bytes(b"sensitive")
    sneaky = fake_home / "Downloads" / "innocent.zip"
    sneaky.symlink_to(outside)

    apply_moves(
        [{"path": str(sneaky), "ext": ".zip", "is_executable": False}],
        str(fake_home), sm,
    )

    # Source must remain untouched; the dangerous move was refused
    assert outside.exists()
    assert sneaky.exists()
    errors = sm.load()["errors"]
    assert any("source resolves outside home" in e["error"] for e in errors)


def test_apply_moves_logs_error_does_not_raise(fake_home, tmp_path):
    """A single bad file must not abort the rest of the batch."""
    sm = StateManager(tmp_path / "state.json")
    bad = fake_home / "Downloads" / "missing.zip"  # never created
    good = _make_file(fake_home / "Downloads" / "real.zip", b"data")

    apply_moves(
        [
            {"path": str(bad), "ext": ".zip", "is_executable": False},
            {"path": str(good), "ext": ".zip", "is_executable": False},
        ],
        str(fake_home), sm,
    )

    # The valid file should still be moved
    assert (fake_home / "Zip Archive" / "real.zip").exists()
    errors = sm.load()["errors"]
    assert len(errors) == 1
    assert "missing.zip" in errors[0]["path"]
