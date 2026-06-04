import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.ai_review import classify_document_text, extract_first_page, record_result
from scripts.state import StateManager


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "state.json"


def test_extract_pdf_returns_text(tmp_path):
    pytest.importorskip("pypdf")
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


def test_classify_legal_reference_document(fake_home):
    pdf = fake_home / "Smith v. Jones 2017 Ill. App..pdf"
    pdf.write_text("Smith v. Jones, 2017 IL App (1st) 123456\nThis is a case citation.")
    result = classify_document_text(extract_first_page(str(pdf)), str(pdf), str(fake_home))
    assert result["category"] == "Legal Reference"
    assert result["folder"] == str(fake_home / "Legal Reference")


def test_classify_medical_files_document(fake_home):
    txt = fake_home / "med recs and bills.txt"
    txt.write_text("Med Recs and Bills\nOrthopaedic surgery records and billing summary.")
    result = classify_document_text(extract_first_page(str(txt)), str(txt), str(fake_home))
    assert result["category"] == "Medical Files"
    assert result["folder"] == str(fake_home / "Medical Files")


def test_classify_unrelated_file_falls_back_to_personal(fake_home):
    md = fake_home / "personal notes.md"
    md.write_text("Miscellaneous notes.")
    result = classify_document_text(extract_first_page(str(md)), str(md), str(fake_home))
    assert result["category"] == "Human Review"
    assert result["folder"] == str(fake_home / "Human Review")


def test_extract_unknown_extension_returns_none(tmp_path):
    f = tmp_path / "unknown.xyz123"
    f.write_bytes(b"\x00\x01\x02binary")
    result = extract_first_page(str(f))
    assert result is None


@pytest.fixture
def fake_home(tmp_path):
    h = tmp_path / "user"
    (h / "Downloads").mkdir(parents=True)
    return h


def test_record_result_saves_to_state(fake_home, state_file):
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "mystery.pdf"),
        result={"category": "Legal", "folder": str(fake_home / "Legal"),
                "confidence": 0.85, "reason": "Contract language"},
        state=sm,
        home_dir=str(fake_home),
    )
    data = sm.load()
    assert len(data["moves"]) == 1
    assert data["moves"][0]["to"] == str(fake_home / "Legal")


def test_record_low_confidence_goes_to_queue(fake_home, state_file):
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "mystery.pdf"),
        result={"category": "Unknown", "folder": str(fake_home / "Human Review"),
                "confidence": 0.2, "reason": "Cannot determine"},
        state=sm,
        home_dir=str(fake_home),
    )
    data = sm.load()
    assert len(data["low_confidence"]) == 1
    assert data["low_confidence"][0]["confidence"] == 0.2


def test_record_rejects_folder_outside_home(fake_home, state_file):
    """AI prompt injection attempt: folder points outside home → forced to low-confidence."""
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "evil.pdf"),
        result={"category": "Legal", "folder": "/etc/cron.d",
                "confidence": 0.95, "reason": "Standard config"},
        state=sm,
        home_dir=str(fake_home),
    )
    data = sm.load()
    assert len(data["moves"]) == 0  # NOT moved
    assert len(data["low_confidence"]) == 1
    assert "unsafe" in data["low_confidence"][0]["reason"].lower()


def test_record_rejects_dotdir_folder(fake_home, state_file):
    """AI returning ~/.ssh/ as folder must be rejected."""
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "evil.pdf"),
        result={"category": "Config", "folder": str(fake_home / ".ssh"),
                "confidence": 0.95, "reason": "SSH config"},
        state=sm,
        home_dir=str(fake_home),
    )
    data = sm.load()
    assert len(data["moves"]) == 0
    assert len(data["low_confidence"]) == 1


def test_record_clamps_high_confidence(fake_home, state_file):
    """Confidence > 1.0 must be clamped to 1.0, not raise."""
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "doc.pdf"),
        result={"category": "Legal", "folder": str(fake_home / "Legal"),
                "confidence": 1.5, "reason": "Very confident"},
        state=sm,
        home_dir=str(fake_home),
    )
    # Treated as valid high confidence (clamped)
    assert len(sm.load()["moves"]) == 1


def test_record_clamps_negative_confidence(fake_home, state_file):
    """Confidence < 0 must be treated as 0 (lowest), routed to low-confidence."""
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "doc.pdf"),
        result={"category": "Legal", "folder": str(fake_home / "Legal"),
                "confidence": -0.5, "reason": "weird"},
        state=sm,
        home_dir=str(fake_home),
    )
    data = sm.load()
    assert len(data["moves"]) == 0
    assert len(data["low_confidence"]) == 1
    assert data["low_confidence"][0]["confidence"] == 0.0


def test_record_handles_non_numeric_confidence(fake_home, state_file):
    """A non-numeric confidence (AI returns a string) must not crash."""
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "doc.pdf"),
        result={"category": "Legal", "folder": str(fake_home / "Legal"),
                "confidence": "high", "reason": "..."},
        state=sm,
        home_dir=str(fake_home),
    )
    # Should treat as 0 and route to low-confidence
    data = sm.load()
    assert len(data["moves"]) == 0
    assert len(data["low_confidence"]) == 1


def test_record_handles_missing_keys(fake_home, state_file):
    """A malformed result missing 'folder' must not crash."""
    sm = StateManager(state_file)
    record_result(
        path=str(fake_home / "Downloads" / "doc.pdf"),
        result={"confidence": 0.9},
        state=sm,
        home_dir=str(fake_home),
    )
    data = sm.load()
    # Missing folder → can't validate → low-confidence with error
    assert len(data["moves"]) == 0
    assert len(data["low_confidence"]) == 1
