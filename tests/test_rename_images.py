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

    with patch("scripts.rename_images.get_exif_date", return_value=None):
        results = scan_for_rename(str(pictures))
    paths = [r["path"] for r in results]
    assert str(pictures / "1000037861.jpg") in paths
    assert str(pictures / "holiday_beach.jpg") not in paths
