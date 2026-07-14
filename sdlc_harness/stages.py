"""Definition of the SDLC stages, in order.

The sequence is data-driven: reorder or extend the SDLC by editing STAGES only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    """One step of the software lifecycle."""

    key: str                      # short id, also used for --start-stage
    title: str                    # human-readable name
    prompt_file: str              # filename under sdlc_harness/prompts/
    output: str                   # artifact filename written under docs/sdlc/
    inputs: tuple[str, ...] = ()  # prior artifact filenames fed in as context
    interview: bool = False       # ask the user questions before running
    applies_code: bool = False    # writes source files into the target project
    runs_tests: bool = False      # executes a command and captures output


STAGES: list[Stage] = [
    Stage("requirements", "Requirements gathering", "requirements.md", "requirements.md",
          interview=True),
    Stage("prd", "Product Requirements Document (PRD)", "prd.md", "prd.md",
          inputs=("requirements.md",)),
    Stage("trd", "Technical Requirements Document (TRD)", "trd.md", "trd.md",
          inputs=("requirements.md", "prd.md"), interview=True),
    Stage("implementation", "Implementation", "implement.md", "implementation-notes.md",
          inputs=("prd.md", "trd.md"), applies_code=True),
    Stage("testing", "Testing", "test.md", "test-report.md",
          inputs=("prd.md", "trd.md", "implementation-notes.md"),
          applies_code=True, runs_tests=True),
]


def stage_index(key: str) -> int:
    """Return the position of a stage by key, or raise if unknown."""
    for i, stage in enumerate(STAGES):
        if stage.key == key:
            return i
    valid = ", ".join(s.key for s in STAGES)
    raise ValueError(f"Unknown stage '{key}'. Valid stages: {valid}")
