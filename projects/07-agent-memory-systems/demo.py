"""Two chat sessions with one long-term memory: the agent remembers you the next day.

    python demo.py                 # fresh, temporary memory database
    python demo.py --db memory.db  # keep the database to inspect it afterwards
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from memory_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
