"""Run the demo without installing anything: python demo.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from swarm.cli import main  # noqa: E402

raise SystemExit(main(sys.argv[1:]))
