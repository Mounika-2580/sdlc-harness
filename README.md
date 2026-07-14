# Generalized SDLC Harness

A standalone, installable tool that wraps an LLM and drives **any** software project through the
software lifecycle — **Requirements → PRD → TRD → Implementation → Testing** — with an approval
gate between every stage. It adapts to the project it's pointed at and works with any LLM, cloud or
local.

Written in Python, but it **operates on projects of any technology** (Node, Java, Go, .NET, Rust,
PHP, Python, …). Python is just the engine; the LLM does the language-specific work.

## What makes it a "harness"
The whole `sdlc_harness/` package is the control layer around the model. The LLM only generates
text; the harness decides *when* it runs, *with what context*, *under what rules*, and *whether it
may proceed*:

| Responsibility | Module |
|---|---|
| Control loop + approval gates (the heart) | `orchestrator.py` |
| Model abstraction (any provider) | `llm/` |
| Brownfield/greenfield + stack detection | `detector.py` |
| SDLC rails (stages + prompts) | `stages.py`, `prompts/` |
| Safe code apply: preview, snapshot, rollback | `changeplan.py` |
| Secrets / PII guardrail | `guardrails.py` |
| Read/write docs, robust JSON, run tests | `artifacts.py` |
| Per-call token/timing log | `logging_util.py` |
| Dynamic, context-aware interview | `interview.py` |
| Resume / run-any-stage | `state.py` |

## Key behaviors
- **Adapts to the project.** Empty folder → *greenfield*: interviews you for a stack. Existing code
  → *brownfield*: detects the stack and keeps every stage inside it (no foreign tech).
- **Any LLM.** Cloud API (Anthropic, OpenAI, OpenRouter, any OpenAI-compatible) **or** local
  (Ollama, LM Studio) — chosen entirely in `.env`.
- **Dynamic questions.** Interview questions are generated per project.
- **Safe code application.** Before writing, it shows a change plan (NEW/OVERWRITE + diff). The
  implementation stage asks approval **before** writing; the testing stage snapshots files and
  **rolls back** if you reject. `--dry-run` previews with zero writes.
- **Secrets/PII guardrail.** Generated files are scanned; anything with a hardcoded key/secret is
  blocked from being written unless you explicitly override (never auto-overridden with `--yes`).
- **Model writes tests, harness runs them** for real; the report shows true pass/fail — never faked.
- **Auto-repair.** On test failure the harness feeds the error back to the model and retries
  (up to `REPAIR_ATTEMPTS`).
- **Adaptive testing gate.** Criticality tier decides strictness: *high* (auth/payments/PII) → hard
  gate (100% + security tests); *standard* → soft (warns, you may proceed); *low/prototype* →
  report-only.
- **Traceability matrix.** After the run it links Requirements → PRD → TRD → Tests and flags gaps.
- **Resume + logging.** Progress in `docs/sdlc/.sdlc-state.json`; every LLM call logged with
  tokens/timing to `docs/sdlc/.harness-log.jsonl`.

## Install (recommended — git repo → CLI)
```powershell
git clone <repo-url> sdlc-harness
cd sdlc-harness
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e .                 # add ".[anthropic]" for the Claude provider; ".[dev]" for tests
Copy-Item .env.example .env      # then edit .env
sdlc <path-to-any-project>       # global command, run from anywhere
```
Prefer not to install? `python run_harness.py <project>` works from the repo with no install.

- **Local / no key:** install [Ollama](https://ollama.com), `ollama pull llama3.2`, keep
  `LLM_PROVIDER=ollama`.
- **Cloud API:** set `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` (+ `LLM_BASE_URL` for
  OpenAI-compatible services).

> Output quality tracks model strength: a strong cloud model produces far better docs/code/tests
> than a tiny local one. The gates, guardrail, and real test execution are what catch weak output.

## Usage
```
sdlc <target-folder>
  --provider anthropic|openai|ollama   # override backend
  --model <id>                         # override model
  --resume                             # continue from last completed stage
  --start-stage <key>                  # start at a stage
  --only-stage <key>                   # run just one stage
  --dry-run                            # preview changes; write no project files
  --yes                                # auto-approve soft gates (CI); can't override HIGH gate/secrets
```
Stages: `requirements | prd | trd | implementation | testing`.
At each gate: `y` = next, `r` = redo, `q` = quit (resume later). Output → `<target>/docs/sdlc/`.

## Develop / test
```powershell
pip install -e ".[dev]"
pytest -q
```

## Safety
Generated content is scanned for secrets/PII before writing. Keep your own `.env` (API keys) out of
version control (`.gitignore` already excludes it).
