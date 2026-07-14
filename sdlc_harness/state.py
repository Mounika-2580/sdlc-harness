"""Run state for resume and run-any-stage.

Progress is persisted to <target>/docs/sdlc/.sdlc-state.json so a run can be stopped
and continued later, a single stage re-run, or the criticality tier remembered.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import ARTIFACT_DIR, STATE_FILE


@dataclass
class RunState:
    """Persisted progress for one target project."""

    project_type: str = ""
    tier: str = ""
    completed: list[str] = field(default_factory=list)
    answers: dict = field(default_factory=dict)

    def mark_complete(self, stage_key: str) -> None:
        if stage_key not in self.completed:
            self.completed.append(stage_key)

    def is_complete(self, stage_key: str) -> bool:
        return stage_key in self.completed


def _state_path(root: Path) -> Path:
    return root / ARTIFACT_DIR / STATE_FILE


def load_state(root: Path) -> RunState:
    path = _state_path(root)
    if not path.is_file():
        return RunState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RunState()
    known = RunState().__dict__.keys()
    return RunState(**{k: v for k, v in data.items() if k in known})


def save_state(root: Path, state: RunState) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
