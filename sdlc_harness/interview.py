"""Interview helpers.

The interview is dynamic: the harness asks the LLM to generate the most relevant
questions for THIS project, then collects the user's answers from the console. This
is what makes the harness adapt its behaviour per project rather than following a
fixed script.
"""

from __future__ import annotations

from .artifacts import extract_json
from .llm.base import LLMProvider

_QUESTION_SYSTEM = (
    "You are a senior analyst preparing for a software project. Given the context, produce the "
    "few most important questions to ask the user for THIS stage. Tailor them to the project's "
    "domain and type. Return ONLY a JSON array of short question strings (max 6). No prose."
)


def _ask_console(question: str) -> str:
    try:
        return input(f"  ? {question}\n    > ").strip()
    except EOFError:
        return ""


def generate_questions(llm: LLMProvider, stage_title: str, context: str,
                       fallback: list[str]) -> list[str]:
    prompt = (f"Stage: {stage_title}\n\nProject context:\n{context}\n\n"
              "Return the JSON array of questions now.")
    try:
        parsed = extract_json(llm.generate(_QUESTION_SYSTEM, prompt))
        if isinstance(parsed, list):
            questions = [str(q).strip() for q in parsed if str(q).strip()]
            if questions:
                return questions[:6]
    except Exception:  # noqa: BLE001 - never let question-gen break the run
        pass
    return fallback


def run_interview(llm: LLMProvider, stage_title: str, context: str,
                  fallback: list[str]) -> str:
    questions = generate_questions(llm, stage_title, context, fallback)
    print(f"\n-- {stage_title}: a few questions (press Enter to skip any) --")
    qa_pairs = [f"Q: {q}\nA: {_ask_console(q) or '(no answer)'}" for q in questions]
    return "\n\n".join(qa_pairs)


REQUIREMENTS_FALLBACK = [
    "In one or two sentences, what is the goal of this project?",
    "Who are the main users?",
    "What are the must-have features?",
    "Any constraints (deadline, compliance, integrations, performance)?",
    "What is explicitly out of scope?",
]

STACK_FALLBACK = [
    "Preferred programming language?",
    "Preferred framework (if any)?",
    "Database / storage needs?",
    "Where will it run (hosting/runtime)?",
]
