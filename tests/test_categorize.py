import stat
import pytest
from pathlib import Path
from scripts.categorize import get_destination, ARCHIVE_EXTS, EMAIL_EXTS, EBOOK_EXTS, IMAGE_EXTS


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "jim"
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
