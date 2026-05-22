import os

import pytest

from scripts.resume_workflow import find_latest_backup
from scripts.resume_workflow import reprocess_review_queue
from scripts.resume_workflow import resume_workflow
from scripts.state import StateManager


def _patch_noop_pipeline(monkeypatch):
    monkeypatch.setattr("scripts.resume_workflow.build_index", lambda home_dir: [{"path": "a"}])
    monkeypatch.setattr("scripts.resume_workflow.save_index", lambda entries, index_path: None)
    monkeypatch.setattr("scripts.resume_workflow.load_index", lambda index_path: [])
    monkeypatch.setattr("scripts.resume_workflow.apply_moves", lambda entries, home_dir, state: [])
    monkeypatch.setattr("scripts.resume_workflow.scan_for_rename", lambda pictures_dir: [])
    monkeypatch.setattr("scripts.resume_workflow.do_rename", lambda path, stem: path)
    monkeypatch.setattr("scripts.resume_workflow.get_mtime_date", lambda path: "2026-05-20")
    monkeypatch.setattr("scripts.resume_workflow.generate_report", lambda state, home_dir, output_path: None)
    monkeypatch.setattr("scripts.resume_workflow.extract_first_page", lambda path: "")


def test_resume_workflow_picks_up_after_backup(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "Pictures").mkdir()
    state_file = tmp_path / "state.json"
    sm = StateManager(state_file)
    sm.mark_phase_complete(0)
    sm.mark_phase_complete(1)
    sm.set_backup_path(str(tmp_path / "backup.tar.gz"))

    _patch_noop_pipeline(monkeypatch)

    result = resume_workflow(str(home), str(state_file))
    out = capsys.readouterr().out

    assert "Resuming from phase 2." in out
    assert result["next_phase"] == 2
    assert 2 in result["completed"]
    assert 8 in result["completed"]
    assert not state_file.exists()


def test_resume_workflow_requires_backup_complete(tmp_path):
    state_file = tmp_path / "state.json"
    sm = StateManager(state_file)
    sm.mark_phase_complete(0)

    with pytest.raises(RuntimeError, match="backup phase is not marked complete"):
        resume_workflow(str(tmp_path), str(state_file))


def test_resume_workflow_bootstraps_missing_state_from_backup(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "Pictures").mkdir()
    backup = tmp_path / "home-backup-2026-05-20.tar.gz"
    backup.write_bytes(b"backup")
    state_file = tmp_path / "state.json"

    _patch_noop_pipeline(monkeypatch)

    result = resume_workflow(str(home), str(state_file), str(backup))
    out = capsys.readouterr().out

    assert f"Bootstrapped state from backup: {backup}" in out
    assert "Resuming from phase 2." in out
    assert result["next_phase"] == 2


def test_find_latest_backup_returns_newest_non_empty_archive(tmp_path):
    root = tmp_path / "mnt"
    older_dir = root / "old"
    newer_dir = root / "new"
    older_dir.mkdir(parents=True)
    newer_dir.mkdir()
    older = older_dir / "home-backup-2026-05-20.tar.gz"
    newer = newer_dir / "home-backup-2026-05-21.tar.gz"
    empty = newer_dir / "home-backup-2026-05-22.tar.gz"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    empty.write_bytes(b"")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    os.utime(empty, (3000, 3000))

    assert find_latest_backup((str(root),)) == newer


def test_phase_5_classifies_and_moves_high_confidence_pdf(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    src = home / "complaint.pdf"
    src.write_text("fake pdf")
    state_file = tmp_path / "state.json"
    unrouted = tmp_path / "unrouted.json"
    unrouted.write_text(f'[{{"path": "{src}", "ext": ".pdf"}}]')

    sm = StateManager(state_file)
    sm.mark_phase_complete(0)
    sm.mark_phase_complete(1)
    sm.mark_phase_complete(2)
    sm.mark_phase_complete(3)
    sm.mark_phase_complete(4)
    sm.set_backup_path(str(tmp_path / "backup.tar.gz"))

    monkeypatch.setattr("scripts.resume_workflow.UNROUTED_PATH", str(unrouted))
    monkeypatch.setattr(
        "scripts.resume_workflow.extract_first_page",
        lambda path: "Circuit Court Plaintiff Defendant Complaint Motion Case No.",
    )

    from scripts.resume_workflow import _run_phase_5

    _run_phase_5(home, sm)
    data = sm.load()

    assert not src.exists()
    assert (home / "Legal Filings" / "complaint.pdf").exists()
    assert data["moves"][-1]["rule"] == "ai:Legal Filings"
    assert data["low_confidence"] == []


def test_phase_5_queues_low_confidence_pdf(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    src = home / "mystery.pdf"
    src.write_text("fake pdf")
    state_file = tmp_path / "state.json"
    unrouted = tmp_path / "unrouted.json"
    unrouted.write_text(f'[{{"path": "{src}", "ext": ".pdf"}}]')
    sm = StateManager(state_file)

    monkeypatch.setattr("scripts.resume_workflow.UNROUTED_PATH", str(unrouted))
    monkeypatch.setattr("scripts.resume_workflow.extract_first_page", lambda path: "")

    from scripts.resume_workflow import _run_phase_5

    _run_phase_5(home, sm)
    data = sm.load()

    assert src.exists()
    assert data["moves"] == []
    assert data["low_confidence"][0]["path"] == str(src)


def test_reprocess_review_queue_reclassifies_placeholders(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    legal = home / "legal.pdf"
    mystery = home / "mystery.pdf"
    legal.write_text("fake pdf")
    mystery.write_text("fake pdf")
    state_file = tmp_path / "state.json"
    sm = StateManager(state_file)
    sm.add_low_confidence(str(legal), str(home / "Review"), 0.0, "awaiting human review")
    sm.add_low_confidence(str(mystery), str(home / "Review"), 0.0, "awaiting human review")

    def fake_extract(path):
        if path.endswith("legal.pdf"):
            return "Circuit Court Plaintiff Defendant Complaint Motion Case No."
        return ""

    monkeypatch.setattr("scripts.resume_workflow.extract_first_page", fake_extract)

    result = reprocess_review_queue(str(home), str(state_file))
    data = sm.load()

    assert result == {"moved": 1, "queued": 1, "skipped": 0}
    assert (home / "Legal Filings" / "legal.pdf").exists()
    assert data["moves"][-1]["rule"] == "ai:Legal Filings"
    assert len(data["low_confidence"]) == 1
    assert data["low_confidence"][0]["path"] == str(mystery)
