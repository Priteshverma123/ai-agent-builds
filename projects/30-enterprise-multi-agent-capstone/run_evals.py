"""Run the eval suite. Exit code 1 if any case fails, so CI can gate merges on it.

Run:  python run_evals.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from capstone.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["evals"]))
