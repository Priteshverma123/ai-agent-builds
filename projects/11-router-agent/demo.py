"""Route six customer messages, then evaluate the router on a labelled set.

    python demo.py
    python demo.py "Can I pay by bank transfer?"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from router_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
