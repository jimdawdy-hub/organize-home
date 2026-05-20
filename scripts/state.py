import json
from datetime import datetime, timezone
from pathlib import Path


def _default_state() -> dict:
    """Return a fresh default state dict. Must be a function to avoid sharing mutable defaults."""
    return {
        "version": 1,
        "started_at": None,
        "backup_path": None,
        "vision": None,
        "completed_phases": [],
        "moves": [],
        "low_confidence": [],
        "errors": [],
    }


DEFAULT_STATE = _default_state()  # For backward compatibility


class StateManager:
    def __init__(self, path: Path | str = None):
        if path is None:
            path = Path.home() / ".organize-home-state.json"
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return _default_state()
        with self.path.open() as f:
            data = json.load(f)
        defaults = _default_state()
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(self.path)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def mark_phase_complete(self, phase: int) -> None:
        data = self.load()
        if phase not in data["completed_phases"]:
            data["completed_phases"].append(phase)
        if data["started_at"] is None:
            data["started_at"] = datetime.now(timezone.utc).isoformat()
        self.save(data)

    def is_phase_complete(self, phase: int) -> bool:
        return phase in self.load()["completed_phases"]

    def add_move(self, from_path: str, to_path: str, phase: int, rule: str) -> None:
        data = self.load()
        data["moves"].append({"from": from_path, "to": to_path, "phase": phase, "rule": rule})
        self.save(data)

    def add_low_confidence(self, path: str, proposed: str, confidence: float, reason: str) -> None:
        data = self.load()
        data["low_confidence"].append({
            "path": path, "proposed": proposed,
            "confidence": confidence, "reason": reason,
        })
        self.save(data)

    def add_error(self, path: str, error: str) -> None:
        data = self.load()
        data["errors"].append({"path": path, "error": error})
        self.save(data)

    def set_vision(self, available: bool) -> None:
        data = self.load()
        data["vision"] = available
        self.save(data)

    def set_backup_path(self, path: str) -> None:
        data = self.load()
        data["backup_path"] = path
        self.save(data)
