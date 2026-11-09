"""One-command demo, no install needed.

Run:  python demo.py                 (scripted on-call answers)
      python demo.py --interactive   (you are the on-call: answer y/n)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from sre_agent.cli import main  # noqa: E402

raise SystemExit(main(sys.argv[1:]))
