"""The harness control loop - the heart of the harness.

Sequences the SDLC stages, injects budgeted context + prior artifacts, drives the LLM
(with per-call logging), previews and safely applies code with snapshot/rollback,
enforces the approval gates (including the adaptive testing gate), auto-repairs failing
tests, and finally builds a traceability matrix. Persists progress for resume.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import artifacts, changeplan, interview, state as state_mod
from .config import (JSON_RETRY_ATTEMPTS, LLMConfig, MAX_DOC_CHARS, REPAIR_ATTEMPTS,
                     TEST_COMMAND_TIMEOUT)
from .detector import ProjectContext, detect
from .llm import get_provider
from .llm.base import LLMProvider
from .logging_util import RunLogger
from .stages import STAGES, Stage, stage_index

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_TIER_SYSTEM = (
    "Classify the criticality of this software project for testing rigor. Answer with EXACTLY one "
    "word: 'high' if it handles security-sensitive concerns (authentication, payments, personal or "
    "health data, access control), 'low' if it is a throwaway/prototype/experiment, otherwise "
    "'standard'."
)
_HIGH_KEYWORDS = ("auth", "login", "password", "payment", "credit card", "bank", "pii",
                  "personal data", "health", "medical", "hipaa", "gdpr", "access control",
                  "encryption", "token", "oauth", "ssn")
_JSON_REFORMAT_SYSTEM = (
    "You returned output that was not valid JSON in the required format. Return ONLY a single JSON "
    "object with keys 'files' (array of {path, content}), 'command', and 'notes'. No prose, no fences "
    "other than one ```json block."
)


class Orchestrator:
    """Drives one target project through the SDLC stages."""

    def __init__(self, target: Path, cfg: LLMConfig, *, auto_yes: bool = False,
                 dry_run: bool = False) -> None:
        self.root = target.resolve()
        self.cfg = cfg
        self.auto_yes = auto_yes
        self.dry_run = dry_run
        self.llm: LLMProvider = get_provider(cfg)
        self.state = state_mod.load_state(self.root)
        self.logger = RunLogger(self.root)
        self.seq = 0
        self.ctx: ProjectContext | None = None
        self._last_test_result: artifacts.CommandResult | None = None

    # -- public entry ---------------------------------------------------------

    def run(self, *, start_stage: str | None = None, only_stage: str | None = None,
            resume: bool = False) -> None:
        self.ctx = detect(self.root)
        if self.state.project_type and self.state.project_type != self.ctx.type:
            print(f"(resuming as {self.state.project_type} from prior run; "
                  f"on-disk now looks {self.ctx.type})")
            self.ctx.type = self.state.project_type
        self.state.project_type = self.ctx.type

        print("\n=== SDLC Harness ===")
        print(f"Target : {self.root}")
        how = "auto-detected" if self.cfg.autodetected else "configured"
        print(f"Model  : {self.llm.label} via '{self.cfg.provider}' ({how})"
              + ("  [DRY-RUN: no files written]" if self.dry_run else ""))
        print(f"Detected project type: {self.ctx.type.upper()}")
        if self.ctx.type == "brownfield" and self.ctx.ecosystems:
            print(f"Detected stack: {', '.join(self.ctx.ecosystems)}")

        stages = self._select_stages(start_stage, only_stage, resume)
        if not stages:
            print("Nothing to do (all selected stages already complete). Use --start-stage to redo.")
            return

        for stage in stages:
            if not self._run_stage(stage):
                print("\nStopped. Re-run with --resume to continue.")
                return

        if not self.dry_run:
            self._build_traceability()
        print("\nAll stages complete. Artifacts are in:", self.root / "docs" / "sdlc")

    # -- stage selection ------------------------------------------------------

    def _select_stages(self, start_stage, only_stage, resume) -> list[Stage]:
        if only_stage:
            return [STAGES[stage_index(only_stage)]]
        begin = 0
        if start_stage:
            begin = stage_index(start_stage)
        elif resume:
            for i, s in enumerate(STAGES):
                if self.state.is_complete(s.key):
                    begin = i + 1
        return STAGES[begin:]

    # -- LLM call with logging -----------------------------------------------

    def _generate(self, stage_key: str, system: str, prompt: str) -> str:
        t0 = time.perf_counter()
        reply = self.llm.generate(system, prompt)
        elapsed = time.perf_counter() - t0
        self.seq += 1
        self.logger.log(seq=self.seq, stage=stage_key, provider=self.cfg.provider,
                        model=self.cfg.model, prompt_chars=len(system) + len(prompt),
                        response_chars=len(reply), elapsed_s=elapsed, usage=self.llm.last_usage)
        return reply

    # -- one stage ------------------------------------------------------------

    def _run_stage(self, stage: Stage) -> bool:
        assert self.ctx is not None
        while True:  # loop supports the 'redo' gate option
            print(f"\n--- Stage: {stage.title} ---")
            interview_block = self._maybe_interview(stage)
            system = self._load_prompt(stage.prompt_file)
            user_prompt = self._build_prompt(stage, interview_block)

            print("Generating (this may take a moment)...")
            reply = self._generate(stage.key, system, user_prompt)

            if stage.applies_code:
                decision = self._run_code_stage(stage, reply)
            else:
                artifacts.write_artifact(self.root, stage.output, self._doc_header(stage) + reply)
                print(f"Wrote: {self.root / 'docs' / 'sdlc' / stage.output}")
                decision = self._gate("Approve this stage?")

            if decision == "y":
                self.state.mark_complete(stage.key)
                state_mod.save_state(self.root, self.state)
                return True
            if decision == "q":
                state_mod.save_state(self.root, self.state)
                return False
            print("Redoing this stage...")

    def _run_code_stage(self, stage: Stage, reply: str) -> str:
        """Handle implementation/testing: preview, guardrail, apply/rollback, tests."""
        files, command, notes, reply = self._parse_with_retry(stage.key, reply,
                                                               self._load_prompt(stage.prompt_file))
        if not files:
            print("No file changes were parsed from the model output (see artifact).")
            artifacts.write_artifact(self.root, stage.output, self._doc_header(stage) + reply)
            return self._gate("No code produced. Approve anyway?")

        plan = changeplan.build_plan(self.root, files)
        print("Planned changes:")
        print(changeplan.render_plan(plan))

        if plan.blocking_findings:
            print("\n[!] Potential secrets/PII in generated files:")
            for path, f in plan.blocking_findings:
                print(f"    {path}: {f.label} ({f.snippet})")
            if not self._allow_secrets():
                print("Skipping apply due to guardrail. Fix and redo.")
                artifacts.write_artifact(self.root, stage.output,
                                         self._doc_header(stage) + "GUARDRAIL BLOCKED\n\n" + notes)
                return self._gate("Guardrail blocked. Redo?", default_yes=False)

        if self.dry_run:
            print("[DRY-RUN] not writing files.")
            artifacts.write_artifact(self.root, stage.output, self._doc_header(stage) + notes)
            return "y"

        if not stage.runs_tests:
            # Implementation: approve BEFORE writing anything.
            decision = self._gate("Apply these changes to the project?")
            if decision != "y":
                return decision
            changeplan.apply_plan(plan, stage.key)
            print(f"Applied {len(files)} file(s).")
            artifacts.write_artifact(self.root, stage.output, self._doc_header(stage) + notes)
            return "y"

        # Testing: must write + run to know the result; snapshot so reject can roll back.
        snap = changeplan.apply_plan(plan, stage.key)
        command, result = self._test_with_repair(stage, command, files)
        report = self._test_report(stage, notes, result)
        artifacts.write_artifact(self.root, stage.output, report)
        print(f"Wrote: {self.root / 'docs' / 'sdlc' / stage.output}")

        decision = self._testing_gate(result)
        if decision != "y":
            changeplan.restore(snap, stage.key)
            print("Rolled back test-stage file writes.")
        return decision

    def _parse_with_retry(self, stage_key: str, reply: str, _system: str):
        files, command, notes = artifacts.parse_file_changes(reply)
        attempts = 0
        while not files and attempts < JSON_RETRY_ATTEMPTS:
            attempts += 1
            print(f"Model output was not valid JSON; asking it to reformat ({attempts})...")
            reply = self._generate(stage_key, _JSON_REFORMAT_SYSTEM,
                                   "Reformat your previous output as the required JSON only:\n\n" + reply)
            files, command, notes = artifacts.parse_file_changes(reply)
        return files, command, notes, reply

    def _test_with_repair(self, stage: Stage, command, files):
        result = self._run_tests(command)
        attempts = 0
        while not result.passed and attempts < REPAIR_ATTEMPTS:
            attempts += 1
            print(f"Tests failed - auto-repair attempt {attempts}/{REPAIR_ATTEMPTS}...")
            repair_prompt = (
                "The tests failed. Fix the code and/or tests so they pass. Keep the same stack.\n\n"
                f"Test command: {command}\n\nActual output:\n{result.output[:4000]}\n\n"
                "Return ONLY the JSON object with the corrected files, command, and notes."
            )
            reply = self._generate(stage.key, self._load_prompt(stage.prompt_file), repair_prompt)
            new_files, new_cmd, _ = artifacts.parse_file_changes(reply)
            if not new_files:
                print("Repair produced no parseable files; stopping repair loop.")
                break
            plan = changeplan.build_plan(self.root, new_files)
            if plan.blocking_findings and not self._allow_secrets():
                print("Repair blocked by guardrail; stopping repair loop.")
                break
            changeplan.apply_plan(plan, stage.key)
            command = new_cmd or command
            result = self._run_tests(command)
        return command, result

    def _run_tests(self, command):
        if not command:
            self._last_test_result = None
            print("No test command was provided by the model; skipped execution.")
            return artifacts.CommandResult("(none)", -1, "No test command provided.")
        print(f"Running tests: {command}")
        result = artifacts.run_command(self.root, command, timeout=TEST_COMMAND_TIMEOUT)
        self._last_test_result = result
        print(f"Test command exited {result.returncode} "
              f"({'PASSED' if result.passed else 'FAILED'}).")
        return result

    # -- helpers --------------------------------------------------------------

    def _maybe_interview(self, stage: Stage) -> str:
        if not stage.interview:
            return ""
        assert self.ctx is not None
        if stage.key == "trd" and self.ctx.type == "brownfield":
            return ""
        fallback = interview.STACK_FALLBACK if stage.key == "trd" else interview.REQUIREMENTS_FALLBACK
        block = interview.run_interview(self.llm, stage.title, self.ctx.to_prompt(), fallback)
        self.state.answers[stage.key] = block
        return block

    def _load_prompt(self, name: str) -> str:
        return (PROMPTS_DIR / name).read_text(encoding="utf-8")

    def _build_prompt(self, stage: Stage, interview_block: str) -> str:
        assert self.ctx is not None
        parts = [self.ctx.to_prompt()]
        for dep in stage.inputs:
            doc = artifacts.read_artifact(self.root, dep)
            if doc:
                parts.append(f"=== {dep} (prior stage output) ===\n{self._budget(doc)}")
        if interview_block:
            parts.append(f"=== User interview answers ===\n{interview_block}")
        if stage.runs_tests:
            parts.append(f"=== Testing criticality tier ===\n{self._tier()} "
                         "(High=100% pass + security/negative tests required)")
        return "\n\n".join(parts)

    @staticmethod
    def _budget(doc: str) -> str:
        """Cap an injected document so large repos don't overflow the context window."""
        if len(doc) <= MAX_DOC_CHARS:
            return doc
        head = doc[:MAX_DOC_CHARS]
        return head + f"\n\n... [truncated {len(doc) - MAX_DOC_CHARS} chars to fit context]"

    def _tier(self) -> str:
        if self.state.tier:
            return self.state.tier
        context = "\n".join(
            artifacts.read_artifact(self.root, f) for f in ("requirements.md", "prd.md", "trd.md"))
        tier = "standard"
        try:
            reply = self._generate("tier", _TIER_SYSTEM, context or "No documents yet.").strip().lower()
            for candidate in ("high", "low", "standard"):
                if candidate in reply:
                    tier = candidate
                    break
        except Exception:  # noqa: BLE001
            lowered = context.lower()
            if any(k in lowered for k in _HIGH_KEYWORDS):
                tier = "high"
        self.state.tier = tier
        return tier

    def _doc_header(self, stage: Stage) -> str:
        return f"<!-- Stage: {stage.title} | project: {self.state.project_type} -->\n"

    def _test_report(self, stage: Stage, notes: str, result) -> str:
        tier = self._tier()
        lines = [self._doc_header(stage), notes,
                 "\n\n## Harness test execution",
                 f"- Criticality tier: **{tier}**",
                 f"- Command: `{result.command}`",
                 f"- Exit code: {result.returncode} ({'PASSED' if result.passed else 'FAILED'})",
                 f"\n### Actual output\n```\n{result.output[:6000]}\n```"]
        return "\n".join(lines)

    def _build_traceability(self) -> None:
        """Final artifact: link requirements -> PRD -> TRD -> tests. Best-effort."""
        docs = {f: artifacts.read_artifact(self.root, f)
                for f in ("requirements.md", "prd.md", "trd.md", "test-report.md")}
        if not any(docs.values()):
            return
        try:
            body = "\n\n".join(f"=== {k} ===\n{self._budget(v)}" for k, v in docs.items() if v)
            system = ("Build a Markdown traceability matrix linking requirements (FR-#) -> PRD "
                      "features (F-#) -> TRD tasks (T-#) -> tests. Add a 'Coverage gaps' section for "
                      "anything unlinked or untested. Return ONLY Markdown.")
            reply = self._generate("traceability", system, body)
            artifacts.write_artifact(self.root, "traceability.md", reply)
            print(f"Wrote: {self.root / 'docs' / 'sdlc' / 'traceability.md'}")
        except Exception as exc:  # noqa: BLE001
            print(f"(traceability matrix skipped: {exc})")

    # -- gates ----------------------------------------------------------------

    def _allow_secrets(self) -> bool:
        if self.auto_yes:
            return False  # never auto-write flagged secrets
        return input("Type 'override' to write flagged files anyway, anything else to skip: "
                     ).strip().lower() == "override"

    def _testing_gate(self, result) -> str:
        tier = self._tier()
        passed = result.passed
        if tier == "low":
            print("[tier: low] report-only - not blocking.")
            return "y" if self.auto_yes else self._prompt_gate("Continue?", default_yes=True)
        if tier == "standard":
            if not passed:
                print("[tier: standard] tests did not fully pass - SOFT gate: you may still proceed.")
            return "y" if self.auto_yes else self._prompt_gate("Approve testing stage?")
        # high -> hard gate
        if passed:
            return "y" if self.auto_yes else self._prompt_gate("Approve testing stage?")
        print("[tier: HIGH] tests failed - HARD gate. Cannot proceed unless you explicitly override.")
        if self.auto_yes:
            print("Auto-yes cannot override a HIGH hard gate. Stopping.")
            return "q"
        choice = input("Type 'override' to force past, 'r' to redo, anything else to quit: ").strip().lower()
        return {"override": "y", "r": "r"}.get(choice, "q")

    def _gate(self, question: str, *, default_yes: bool = False) -> str:
        if self.auto_yes:
            print("[auto-approve] advancing.")
            return "y"
        return self._prompt_gate(question, default_yes=default_yes)

    @staticmethod
    def _prompt_gate(question: str, *, default_yes: bool = False) -> str:
        raw = input(f"{question} [y = next / r = redo / q = quit]: ").strip().lower()
        if raw in ("y", "yes"):
            return "y"
        if raw in ("r", "redo"):
            return "r"
        if raw in ("q", "quit"):
            return "q"
        if raw == "":
            return "y" if default_yes else "q"
        return "q"
