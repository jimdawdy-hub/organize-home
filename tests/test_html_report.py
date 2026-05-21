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
    assert "2 files moved" in html or "2 moves" in html or ">2<" in html


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


def test_report_escapes_xss_in_filenames(tmp_path, sample_state):
    """Filenames containing HTML/JS must be escaped, not interpreted."""
    sample_state["moves"].append({
        "from": "/home/user/Downloads/<script>alert('xss')</script>.pdf",
        "to": "/home/user/Legal/<script>alert('xss')</script>.pdf",
        "phase": 5, "rule": "ai:Legal",
    })
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html


def test_report_escapes_xss_in_ai_reason(tmp_path, sample_state):
    """AI-generated reason field must be escaped — defends against prompt injection."""
    sample_state["low_confidence"][0]["reason"] = '<img src=x onerror="alert(1)">'
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    assert '<img src=x onerror' not in html
    assert "&lt;img src=x onerror" in html


def test_report_escapes_xss_in_directory_names(tmp_path, sample_state):
    """Directory names rendered in tree must be escaped."""
    home = tmp_path / "fake_home"
    (home / "<script>evil</script>").mkdir(parents=True)
    output = tmp_path / "home-index.html"
    generate_report(sample_state, str(home), str(output))
    html = output.read_text()
    assert "<script>evil" not in html


def test_report_shell_safe_mv_command(tmp_path, sample_state):
    """The copyable mv command must safely quote filenames containing single quotes."""
    sample_state["low_confidence"][0]["path"] = "/home/user/Downloads/it's a file.pdf"
    sample_state["low_confidence"][0]["proposed"] = "/home/user/Legal"
    output = tmp_path / "home-index.html"
    generate_report(sample_state, "/home/user", str(output))
    html = output.read_text()
    # Should NOT contain unsafe quoting that would break out of single quotes
    assert "mv 'it's" not in html
    assert "mv '/home/user/Downloads/it's" not in html


def test_report_handles_empty_state(tmp_path):
    """Empty state should still produce valid HTML without crashing."""
    empty = {
        "version": 1, "started_at": None, "backup_path": None, "vision": None,
        "completed_phases": [], "moves": [], "low_confidence": [], "errors": [],
    }
    output = tmp_path / "home-index.html"
    generate_report(empty, str(tmp_path), str(output))
    html = output.read_text()
    assert "<!DOCTYPE html>" in html
    assert "Home Directory Index" in html
