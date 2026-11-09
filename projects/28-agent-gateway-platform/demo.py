"""One-command demo, no install needed: python demo.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from gateway.cli import main  # noqa: E402

raise SystemExit(main(["demo"]))
