"""Project detection: brownfield vs greenfield, plus a stack summary.

The detector is data-driven (see config.DETECTION_MAP) and holds no language-specific
logic. It produces a ProjectContext that is injected into every stage prompt so the
LLM can conform to whatever technology is actually present.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from .config import DETECTION_MAP, IGNORE_DIRS, SOURCE_EXTENSIONS

_MAX_TREE_ENTRIES = 60
_MAX_MANIFEST_CHARS = 1500


@dataclass
class ProjectContext:
    """Everything the harness knows about the target project."""

    root: Path
    type: str                                   # "brownfield" | "greenfield"
    ecosystems: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    tree: str = ""
    manifest_snippets: str = ""

    def to_prompt(self) -> str:
        """Render the context as a text block for injection into stage prompts."""
        if self.type == "greenfield":
            return (
                "PROJECT TYPE: greenfield (empty / no existing code).\n"
                "There is no existing stack - the technology will be chosen with the user."
            )
        lines = [
            "PROJECT TYPE: brownfield (existing code present).",
            f"DETECTED ECOSYSTEMS: {', '.join(self.ecosystems) or 'unknown'}",
            f"MANIFESTS FOUND: {', '.join(self.manifests) or 'none'}",
            "",
            "FOLDER STRUCTURE (top levels):",
            self.tree or "(empty)",
        ]
        if self.manifest_snippets:
            lines += ["", "KEY MANIFEST EXCERPTS:", self.manifest_snippets]
        lines += [
            "",
            "RULE: Conform to this existing stack and conventions. Do NOT introduce new "
            "languages, frameworks, or tools that are not already present.",
        ]
        return "\n".join(lines)


def _match_ecosystem(filename: str) -> str | None:
    if filename in DETECTION_MAP:
        return DETECTION_MAP[filename]
    for pattern, label in DETECTION_MAP.items():
        if "*" in pattern and fnmatch.fnmatch(filename, pattern):
            return label
    return None


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _build_tree(root: Path) -> str:
    entries: list[str] = []
    try:
        top = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return ""
    for item in top:
        if item.name in IGNORE_DIRS:
            continue
        if item.is_dir():
            entries.append(f"{item.name}/")
            try:
                children = sorted(item.iterdir(), key=lambda p: p.name.lower())
            except OSError:
                children = []
            for child in children[:8]:
                if child.name in IGNORE_DIRS:
                    continue
                entries.append(f"  {child.name}{'/' if child.is_dir() else ''}")
        else:
            entries.append(item.name)
        if len(entries) >= _MAX_TREE_ENTRIES:
            entries.append("...")
            break
    return "\n".join(entries)


def _collect_manifest_snippets(root: Path, manifests: list[str]) -> str:
    chunks: list[str] = []
    budget = _MAX_MANIFEST_CHARS
    for rel in manifests[:4]:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = text[: min(budget, 600)].strip()
        if not excerpt:
            continue
        chunks.append(f"--- {rel} ---\n{excerpt}")
        budget -= len(excerpt)
        if budget <= 0:
            break
    return "\n\n".join(chunks)


def detect(target: Path) -> ProjectContext:
    """Classify the target folder and gather a stack summary for brownfield."""
    root = target.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Target is not a directory: {root}")

    ecosystems: list[str] = []
    manifests: list[str] = []
    has_source = False

    for path in _iter_files(root):
        # Never let the harness's own output folder influence detection.
        if "docs" in path.parts and "sdlc" in path.parts:
            continue
        label = _match_ecosystem(path.name)
        if label:
            if label not in ecosystems:
                ecosystems.append(label)
            manifests.append(str(path.relative_to(root)))
        if path.suffix in SOURCE_EXTENSIONS:
            has_source = True

    is_brownfield = bool(manifests) or has_source
    ctx = ProjectContext(
        root=root,
        type="brownfield" if is_brownfield else "greenfield",
        ecosystems=ecosystems,
        manifests=manifests[:20],
    )
    if is_brownfield:
        ctx.tree = _build_tree(root)
        ctx.manifest_snippets = _collect_manifest_snippets(root, manifests)
    return ctx
