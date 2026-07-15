# Getting Started — SDLC Harness

This guide gets you from zero to running the harness on your own project. No prior setup knowledge
needed — just follow the steps in order.

## What this tool does (30-second version)
You point it at a project folder and it walks that project through the software lifecycle —
**Requirements → PRD → TRD → Implementation → Testing** — one step at a time, asking for your
approval between steps. It works on **any** kind of project and with **any** AI model (a free local
one or a paid cloud one).

---

## 1. Prerequisites
- **Python 3.10 or newer** — check with `python --version`.
- **Git** — to download the tool.
- **An AI model** — pick ONE:
  - **Free / offline:** [Ollama](https://ollama.com) installed and running, then `ollama pull llama3.2`.
  - **Cloud:** an API key from OpenAI, OpenRouter, or Anthropic.

---

## 2. Install (once)
```powershell
git clone https://github.com/Mounika-2580/sdlc-harness
cd sdlc-harness
python -m venv .venv
.venv\Scripts\Activate.ps1      # macOS/Linux: source .venv/bin/activate
pip install -e .
```
After this you have a global `sdlc` command (while the `.venv` is active).

---

## 3. Choose your AI (once)
```powershell
Copy-Item .env.example .env      # macOS/Linux: cp .env.example .env
```
Open `.env` and set it up for the AI you chose:

**Option A — Free local model (Ollama):**
```
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
```

**Option B — Cloud model (OpenAI / OpenRouter):**
```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...your-own-key...
LLM_BASE_URL=https://api.openai.com/v1      # or https://openrouter.ai/api/v1
```

**Option C — Claude (Anthropic):**
```
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-4-8
LLM_API_KEY=sk-ant-...your-own-key...
```
> Use YOUR OWN key. Never commit `.env` — it is already git-ignored.
> Tip: a stronger cloud model produces noticeably better docs/code/tests than a small local one.

---

## 4. Run it on a project
```powershell
sdlc C:\path\to\your-project
```
- **Empty folder** → it detects *greenfield*, asks you a few questions about the stack, then builds.
- **Folder with existing code** → it detects *brownfield*, finds the tech stack, and stays within it.

At each stage it shows you a document/result and asks:
```
Approve this stage? [y = next / r = redo / q = quit]
```
- `y` — continue to the next stage
- `r` — redo this stage (regenerate)
- `q` — stop (you can continue later)

Everything it produces is written into **your project** under `docs/sdlc/`:
`requirements.md`, `prd.md`, `trd.md`, the generated code, `test-report.md`, and `traceability.md`.

---

## 5. Useful options
| Command | What it does |
|---|---|
| `sdlc <folder>` | Run the full lifecycle with gates. |
| `sdlc <folder> --dry-run` | Preview what would change; writes NO project files. |
| `sdlc <folder> --resume` | Continue from where you last stopped. |
| `sdlc <folder> --only-stage trd` | Run just one stage. |
| `sdlc <folder> --start-stage implementation` | Start from a chosen stage. |
| `sdlc <folder> --provider ollama --model llama3.2` | Override the AI for this run. |
| `sdlc <folder> --yes` | Auto-approve soft gates (for automation/CI). |

Stages: `requirements | prd | trd | implementation | testing`.

---

## 6. Verify it works (optional)
```powershell
pip install -e ".[dev]"
pytest -q                    # should print: 17 passed
```

---

## 7. Troubleshooting
| Problem | Fix |
|---|---|
| `sdlc: command not found` | Activate the venv: `.venv\Scripts\Activate.ps1`. Or run `python run_harness.py <folder>`. |
| `Could not reach Ollama...` | Start Ollama (`ollama serve`) and pull the model (`ollama pull llama3.2`). |
| `LLM_API_KEY is required` | You chose a cloud provider — set `LLM_API_KEY` in `.env`. |
| `no model configured` | Set `LLM_MODEL` in `.env` or pass `--model`. |
| Tests fail / weak output | Usually a small local model. Try a stronger cloud model. |

---

## 8. Safety notes
- The harness previews file changes and can roll them back if you reject a stage.
- It scans generated files for secrets/passwords and refuses to write them.
- It runs tests for real and reports true pass/fail — it never fakes success.
