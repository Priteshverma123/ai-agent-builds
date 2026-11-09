"""Entry point: `python run.py demo | evals | serve` (no install needed)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from support_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
