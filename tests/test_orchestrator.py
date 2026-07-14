"""Orchestrator tests using a fake in-memory LLM provider (no network)."""

import json

from sdlc_harness.config import LLMConfig
from sdlc_harness.llm.base import LLMProvider
from sdlc_harness.orchestrator import Orchestrator


class FakeProvider(LLMProvider):
    """Returns canned replies via a responder(system, prompt) -> str callback."""

    def __init__(self, responder):
        super().__init__("fake", "", "", 1024, 0.0, 10)
        self._responder = responder

    def generate(self, system, prompt):
        self.last_usage = {"input_tokens": 10, "output_tokens": 20}
        return self._responder(system, prompt)


def _orch(tmp_path, responder, **kw):
    cfg = LLMConfig(provider="ollama", model="fake")
    o = Orchestrator(tmp_path, cfg, auto_yes=True, **kw)
    o.llm = FakeProvider(responder)
    return o


def test_doc_stage_writes_artifact_and_logs(tmp_path):
    o = _orch(tmp_path, lambda s, p: "PRD BODY")
    o.run(only_stage="prd")
    prd = (tmp_path / "docs" / "sdlc" / "prd.md").read_text()
    assert "PRD BODY" in prd
    assert o.state.is_complete("prd")
    # per-call log written
    log = (tmp_path / "docs" / "sdlc" / ".harness-log.jsonl").read_text().strip().splitlines()
    assert json.loads(log[0])["stage"] == "prd"


def test_implementation_applies_files_after_approval(tmp_path):
    payload = json.dumps({"files": [{"path": "app.py", "content": "print('hi')"}],
                          "command": "", "notes": "built"})
    o = _orch(tmp_path, lambda s, p: f"```json\n{payload}\n```")
    o.run(only_stage="implementation")
    assert (tmp_path / "app.py").read_text() == "print('hi')"


def test_dry_run_writes_no_project_files(tmp_path):
    payload = json.dumps({"files": [{"path": "app.py", "content": "x=1"}], "command": "", "notes": "n"})
    o = _orch(tmp_path, lambda s, p: f"```json\n{payload}\n```", dry_run=True)
    o.run(only_stage="implementation")
    assert not (tmp_path / "app.py").exists()  # nothing written in dry-run


def test_guardrail_blocks_secret_in_auto_yes(tmp_path):
    payload = json.dumps({"files": [{"path": "cfg.py", "content": 'AWS="AKIA1234567890ABCD99"'}],
                          "command": "", "notes": "n"})
    o = _orch(tmp_path, lambda s, p: f"```json\n{payload}\n```")
    o.run(only_stage="implementation")
    assert not (tmp_path / "cfg.py").exists()  # blocked, not written


def test_high_tier_hard_gate_blocks_on_failure(tmp_path):
    o = _orch(tmp_path, lambda s, p: "x")
    o.state.tier = "high"
    from sdlc_harness.artifacts import CommandResult
    assert o._testing_gate(CommandResult("t", 1, "boom")) == "q"   # fail -> blocked
    assert o._testing_gate(CommandResult("t", 0, "ok")) == "y"     # pass -> proceed


def test_low_tier_reports_only(tmp_path):
    o = _orch(tmp_path, lambda s, p: "x")
    o.state.tier = "low"
    from sdlc_harness.artifacts import CommandResult
    assert o._testing_gate(CommandResult("t", 1, "boom")) == "y"   # never blocks
