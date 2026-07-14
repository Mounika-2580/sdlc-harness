"""Command-line entry point for the generalized SDLC harness.

Installed as the `sdlc` command; also runnable as `python -m sdlc_harness`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import load_llm_config
from .orchestrator import Orchestrator
from .stages import STAGES


def _parse_args(argv: list[str]) -> argparse.Namespace:
    keys = [s.key for s in STAGES]
    p = argparse.ArgumentParser(prog="sdlc", description="Generalized SDLC harness.")
    p.add_argument("target", help="Path to the project folder to work on.")
    p.add_argument("--provider", help="LLM provider (anthropic | openai | ollama).")
    p.add_argument("--model", help="Model id override.")
    p.add_argument("--resume", action="store_true", help="Continue from last completed stage.")
    p.add_argument("--start-stage", choices=keys, help="Start from this stage.")
    p.add_argument("--only-stage", choices=keys, help="Run only this stage.")
    p.add_argument("--yes", action="store_true", help="Auto-approve soft gates (CI).")
    p.add_argument("--dry-run", action="store_true", help="Preview changes; write no project files.")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    target = Path(args.target)
    if not target.is_dir():
        print(f"Error: target folder does not exist: {target}", file=sys.stderr)
        return 2

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    cfg = load_llm_config()
    if not cfg.model:
        print("Error: no model configured. Set LLM_MODEL or use --model.", file=sys.stderr)
        return 2

    orch = Orchestrator(target, cfg, auto_yes=args.yes, dry_run=args.dry_run)
    try:
        orch.run(start_stage=args.start_stage, only_stage=args.only_stage, resume=args.resume)
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run with --resume to continue.")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"\nHarness error: {exc}", file=sys.stderr)
        return 1
    return 0


def cli() -> None:
    """Console-script entry point (the installed `sdlc` command)."""
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
