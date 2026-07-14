"""Unit tests for the harness's pure logic (no LLM/network)."""

from pathlib import Path

from sdlc_harness import artifacts, changeplan, guardrails
from sdlc_harness.artifacts import CodeChange
from sdlc_harness.detector import detect
from sdlc_harness.stages import STAGES, stage_index
from sdlc_harness.state import RunState, load_state, save_state


def test_detect_greenfield(tmp_path):
    assert detect(tmp_path).type == "greenfield"


def test_detect_brownfield_node(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    (tmp_path / "index.js").write_text("console.log(1)", encoding="utf-8")
    ctx = detect(tmp_path)
    assert ctx.type == "brownfield"
    assert any("Node" in e for e in ctx.ecosystems)


def test_detect_ignores_own_artifacts(tmp_path):
    # docs/sdlc content must not flip an empty project to brownfield.
    d = tmp_path / "docs" / "sdlc"
    d.mkdir(parents=True)
    (d / "requirements.md").write_text("# reqs", encoding="utf-8")
    assert detect(tmp_path).type == "greenfield"


def test_extract_json_variants():
    assert artifacts.extract_json('```json\n{"a":1}\n```') == {"a": 1}
    assert artifacts.extract_json('noise {"a": [1,2,],} tail') == {"a": [1, 2]}  # trailing commas
    assert artifacts.extract_json("no json here") is None


def test_parse_file_changes():
    reply = '```json\n{"files":[{"path":"a.py","content":"x=1"}],"command":"pytest","notes":"hi"}\n```'
    files, cmd, notes = artifacts.parse_file_changes(reply)
    assert [f.path for f in files] == ["a.py"] and cmd == "pytest" and notes == "hi"


def test_run_command_exit_codes(tmp_path):
    ok = artifacts.run_command(tmp_path, 'python -c "print(2+2)"')
    bad = artifacts.run_command(tmp_path, 'python -c "import sys; sys.exit(3)"')
    assert ok.passed and "4" in ok.output
    assert not bad.passed and bad.returncode == 3


def test_guardrail_flags_and_ignores_placeholder():
    assert guardrails.has_blocking(guardrails.scan('key = "AKIA1234567890ABCD99"'))
    assert not guardrails.has_blocking(guardrails.scan('key = "your-key-here"'))


def test_changeplan_new_vs_overwrite_and_rollback(tmp_path):
    (tmp_path / "keep.txt").write_text("ORIGINAL", encoding="utf-8")
    changes = [CodeChange("keep.txt", "CHANGED"), CodeChange("new.txt", "NEW")]
    plan = changeplan.build_plan(tmp_path, changes)
    statuses = {pf.change.path: pf.status for pf in plan.files}
    assert statuses == {"keep.txt": "OVERWRITE", "new.txt": "NEW"}

    snap = changeplan.apply_plan(plan, "implementation")
    assert (tmp_path / "keep.txt").read_text() == "CHANGED"
    assert (tmp_path / "new.txt").exists()

    changeplan.restore(snap, "implementation")
    assert (tmp_path / "keep.txt").read_text() == "ORIGINAL"   # restored
    assert not (tmp_path / "new.txt").exists()                 # created file removed


def test_changeplan_refuses_escape(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        changeplan.build_plan(tmp_path, [CodeChange("../escape.txt", "x")])


def test_state_roundtrip(tmp_path):
    st = RunState(project_type="greenfield", tier="high", completed=["requirements"])
    save_state(tmp_path, st)
    loaded = load_state(tmp_path)
    assert loaded.project_type == "greenfield" and loaded.is_complete("requirements")


def test_stage_index():
    assert stage_index("testing") == len(STAGES) - 1
