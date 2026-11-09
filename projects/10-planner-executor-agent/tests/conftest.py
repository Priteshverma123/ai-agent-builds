import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

GOAL = (ROOT / "examples" / "goal.txt").read_text(encoding="utf-8").strip()
