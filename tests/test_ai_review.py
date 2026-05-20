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
    md.write_text("# Family Budget\n\nMonthly expenses for the name-labeled household.")
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
    assert len(data["moves"]) == 1
    assert data["moves"][0]["from"] == "/home/user/Downloads/mystery.pdf"
    assert data["moves"][0]["to"] == "/home/user/Legal"


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
