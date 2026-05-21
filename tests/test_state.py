import json
import pytest
from pathlib import Path
from scripts.state import StateManager, StateCorruptError, SCHEMA_VERSION


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


def test_load_raises_on_malformed_json(state_file):
    state_file.write_text("{ this is not json")
    sm = StateManager(state_file)
    with pytest.raises(StateCorruptError, match="could not parse"):
        sm.load()


def test_load_raises_on_wrong_top_level_type(state_file):
    state_file.write_text('["not", "an", "object"]')
    sm = StateManager(state_file)
    with pytest.raises(StateCorruptError, match="JSON object"):
        sm.load()


def test_load_raises_on_field_type_mismatch(state_file):
    state_file.write_text(json.dumps({"version": 1, "moves": "not a list"}))
    sm = StateManager(state_file)
    with pytest.raises(StateCorruptError, match="moves.*expected list"):
        sm.load()


def test_load_raises_on_unsupported_version(state_file):
    state_file.write_text(json.dumps({"version": 999, "moves": [], "low_confidence": [],
                                       "errors": [], "completed_phases": []}))
    sm = StateManager(state_file)
    with pytest.raises(StateCorruptError, match="unsupported state version"):
        sm.load()


def test_add_error_records_to_state(state_file):
    sm = StateManager(state_file)
    sm.add_error("/home/user/Downloads/bad.pdf", "permission denied")
    data = sm.load()
    assert len(data["errors"]) == 1
    assert data["errors"][0]["path"] == "/home/user/Downloads/bad.pdf"
    assert data["errors"][0]["error"] == "permission denied"


def test_started_at_only_set_on_first_phase(state_file):
    sm = StateManager(state_file)
    sm.mark_phase_complete(0)
    first_start = sm.load()["started_at"]
    assert first_start is not None
    sm.mark_phase_complete(1)
    sm.mark_phase_complete(2)
    # started_at must remain the original value
    assert sm.load()["started_at"] == first_start
