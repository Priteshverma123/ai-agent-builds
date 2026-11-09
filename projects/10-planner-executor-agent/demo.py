"""Plan a trip, hit a sold-out hotel, re-plan, and finish the job.

    python demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from planner_executor.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
