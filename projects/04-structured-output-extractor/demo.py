"""Run the demo without installing anything: `python demo.py` (add --help for options)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from extractor.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
