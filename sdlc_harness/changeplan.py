"""Change plan, preview, snapshot and rollback for code the model produces.

This turns the gate into a real checkpoint:
- build_plan() classifies each file as NEW or OVERWRITE and produces a short diff.
- render_plan() shows the user what will change (used for preview / --dry-run).
- Snapshot captures overwritten originals + records created files; restore() puts the
  target back exactly as it was, so rejecting a stage (redo/quit) undoes every write.
All writes are sandboxed to the target root.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from . import guardrails
from .artifacts import CodeChange
from .config import ARTIFACT_DIR, BACKUP_DIR

_MAX_DIFF_LINES = 25


@dataclass
class PlannedFile:
    change: CodeChange
    exists: bool
    diff: str
    findings: list[guardrails.Finding] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "OVERWRITE" if self.exists else "NEW"


@dataclass
class ChangePlan:
    root: Path
    files: list[PlannedFile]

    @property
    def blocking_findings(self) -> list[tuple[str, guardrails.Finding]]:
        out = []
        for pf in self.files:
            for f in pf.findings:
                if f.severity == "high":
                    out.append((pf.change.path, f))
        return out


def _resolve(root: Path, rel: str) -> Path:
    dest = (root / Path(rel)).resolve()
    root_res = root.resolve()
    if dest != root_res and root_res not in dest.parents:
        raise ValueError(f"Refusing to write outside the target: {rel}")
    return dest


def build_plan(root: Path, changes: list[CodeChange]) -> ChangePlan:
    """Classify changes and scan each for secrets/PII."""
    planned: list[PlannedFile] = []
    for ch in changes:
        dest = _resolve(root, ch.path)
        exists = dest.is_file()
        old = dest.read_text(encoding="utf-8", errors="replace") if exists else ""
        diff = _short_diff(old, ch.content, ch.path) if exists else ""
        planned.append(PlannedFile(change=ch, exists=exists, diff=diff,
                                    findings=guardrails.scan(ch.content)))
    return ChangePlan(root=root, files=planned)


def _short_diff(old: str, new: str, path: str) -> str:
    lines = list(difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="",
    ))
    if len(lines) > _MAX_DIFF_LINES:
        lines = lines[:_MAX_DIFF_LINES] + [f"... (+{len(lines) - _MAX_DIFF_LINES} more diff lines)"]
    return "\n".join(lines)


def render_plan(plan: ChangePlan) -> str:
    if not plan.files:
        return "  (no files)"
    out: list[str] = []
    for pf in plan.files:
        flag = "  [!] secrets/PII" if pf.findings else ""
        out.append(f"  {pf.status:9} {pf.change.path} ({len(pf.change.content)} chars){flag}")
    return "\n".join(out)


# --- snapshot / apply / restore ----------------------------------------------


@dataclass
class Snapshot:
    root: Path
    created: list[str] = field(default_factory=list)   # files that did not exist before
    backed_up: list[str] = field(default_factory=list)  # overwritten files (originals saved)


def _backup_root(root: Path, stage_key: str) -> Path:
    return root / ARTIFACT_DIR / BACKUP_DIR / stage_key


def apply_plan(plan: ChangePlan, stage_key: str) -> Snapshot:
    """Write the planned files, snapshotting anything overwritten so it can be undone."""
    snap = Snapshot(root=plan.root)
    backups = _backup_root(plan.root, stage_key)
    for pf in plan.files:
        dest = _resolve(plan.root, pf.change.path)
        if pf.exists:
            bpath = backups / pf.change.path
            bpath.parent.mkdir(parents=True, exist_ok=True)
            bpath.write_text(dest.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            snap.backed_up.append(pf.change.path)
        else:
            snap.created.append(pf.change.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(pf.change.content, encoding="utf-8")
    return snap


def restore(snap: Snapshot, stage_key: str) -> None:
    """Undo an applied plan: delete created files, restore overwritten originals."""
    for rel in snap.created:
        dest = _resolve(snap.root, rel)
        if dest.is_file():
            dest.unlink()
    backups = _backup_root(snap.root, stage_key)
    for rel in snap.backed_up:
        bpath = backups / rel
        dest = _resolve(snap.root, rel)
        if bpath.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(bpath.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
