"""Entry point: `python run.py demo | run | eval [--inbox ... --client ... --out ...]`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from intake.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
