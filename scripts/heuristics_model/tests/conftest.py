from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HEURISTICS_SRC = ROOT / "scripts" / "heuristics_model" / "src"

for path in (ROOT, HEURISTICS_SRC, ROOT / "scripts"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
