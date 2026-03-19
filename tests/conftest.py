from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEURISTICS_SRC = ROOT / "scripts" / "heuristics_model" / "src"
SCRIPTS_DIR = ROOT / "scripts"

for path in (ROOT, HEURISTICS_SRC, SCRIPTS_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
