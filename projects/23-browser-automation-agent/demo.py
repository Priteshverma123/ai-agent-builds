"""An agent shops on a local website it has never seen, by reading the accessibility tree.

    python demo.py                    # compact trace
    python demo.py --show-snapshots   # print every snapshot the model sees
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from browser_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
