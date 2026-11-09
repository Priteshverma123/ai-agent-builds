"""Three agents, two HTTP servers: a planner discovers two specialists and delegates to them over A2A.

    python demo.py
    python demo.py "I live in Sydney and I'm flying to Lisbon in July with 1200 dollars. What's that in euros and what should I pack?"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from a2a_local.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
