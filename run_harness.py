"""Backwards-compatible launcher: `python run_harness.py <target> [options]`.

The real code lives in the installable `sdlc_harness` package (use the `sdlc`
command after `pip install -e .`). This shim lets you run without installing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sdlc_harness.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
