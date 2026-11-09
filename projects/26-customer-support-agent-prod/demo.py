"""One-command demo, no install needed: `python demo.py` (same as `python run.py demo`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from support_agent.cli import main  # noqa: E402

raise SystemExit(main(["demo"]))
