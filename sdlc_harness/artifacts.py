"""Artifact and command I/O for the harness.

- read/write the SDLC docs under <target>/docs/sdlc/
- robustly extract the LLM's language-neutral file payload ([{path, content}])
- run a test/build command in the target and capture the real output
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import ARTIFACT_DIR

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def artifact_dir(root: Path) -> Path:
    path = root / ARTIFACT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_artifact(root: Path, filename: str, content: str) -> Path:
    path = artifact_dir(root) / filename
    path.write_text(content, encoding="utf-8")
    return path


def read_artifact(root: Path, filename: str) -> str:
    path = artifact_dir(root) / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _strip_trailing_commas(text: str) -> str:
    """Tolerate a common LLM JSON mistake: trailing commas before } or ]."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def extract_json(text: str) -> object | None:
    """Best-effort extraction of a JSON value from an LLM reply.

    Order: fenced ```json blocks, then the widest balanced {...}/[...] span. Each
    candidate is retried with trailing-comma repair before giving up.
    """
    candidates: list[str] = list(_FENCE_RE.findall(text))
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for cand in candidates:
        for attempt in (cand, _strip_trailing_commas(cand)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
    return None


@dataclass
class CodeChange:
    """One file the model wants to create or overwrite in the target."""

    path: str
    content: str


def parse_file_changes(text: str) -> tuple[list[CodeChange], str | None, str]:
    """Parse the implementer/test payload into (files, command, notes)."""
    data = extract_json(text)
    files: list[CodeChange] = []
    command: str | None = None
    notes = ""

    records = []
    if isinstance(data, dict):
        records = data.get("files", [])
        command = data.get("command") or data.get("test") or data.get("run")
        notes = str(data.get("notes", ""))
    elif isinstance(data, list):
        records = data

    for rec in records:
        if isinstance(rec, dict) and "path" in rec and "content" in rec:
            files.append(CodeChange(path=str(rec["path"]), content=str(rec["content"])))
    return files, command, notes


@dataclass
class CommandResult:
    command: str
    returncode: int
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_command(root: Path, command: str, timeout: int = 300) -> CommandResult:
    """Run a shell command in the target folder and capture combined output."""
    try:
        proc = subprocess.run(
            command, cwd=str(root), shell=True,
            capture_output=True, text=True, timeout=timeout,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return CommandResult(command=command, returncode=proc.returncode, output=output)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(command, -1,
                             f"TIMEOUT after {timeout}s\n{exc.stdout or ''}{exc.stderr or ''}")
    except OSError as exc:
        return CommandResult(command, -1, f"Failed to run: {exc}")
