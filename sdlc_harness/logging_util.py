"""Per-call LLM logging: tokens, timing, and a rough cost estimate.

Every model call is appended as one JSON line to <target>/docs/sdlc/.harness-log.jsonl
so a run is auditable. Token counts use provider-reported usage when available and
fall back to a chars/4 estimate otherwise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import ARTIFACT_DIR, LOG_FILE


def estimate_tokens(text: str) -> int:
    """Rough token estimate when the provider reports none (~4 chars/token)."""
    return max(1, len(text) // 4)


@dataclass
class RunLogger:
    root: Path

    def _path(self) -> Path:
        p = self.root / ARTIFACT_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p / LOG_FILE

    def log(self, *, seq: int, stage: str, provider: str, model: str,
            prompt_chars: int, response_chars: int, elapsed_s: float,
            usage: dict | None) -> dict:
        """Append one call record and return it (also used for the run summary)."""
        usage = usage or {}
        record = {
            "seq": seq,
            "stage": stage,
            "provider": provider,
            "model": model,
            "prompt_chars": prompt_chars,
            "response_chars": response_chars,
            "elapsed_s": round(elapsed_s, 2),
            "input_tokens": usage.get("input_tokens") or estimate_tokens(" " * prompt_chars),
            "output_tokens": usage.get("output_tokens") or estimate_tokens(" " * response_chars),
            "tokens_estimated": not usage,
        }
        with self._path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return record
