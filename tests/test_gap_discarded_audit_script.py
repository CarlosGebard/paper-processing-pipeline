from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "audit_gap_rag_discarded_today.py"
SPEC = importlib.util.spec_from_file_location("audit_gap_rag_discarded_today", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_move_gap_rag_discards_for_date_moves_only_gap_rag_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "discarded"
    source_dir.mkdir()

    gap_file = source_dir / "gap.json"
    gap_file.write_text(
        json.dumps(
            {
                "doi": "10.1000/gap",
                "title": "Gap paper",
                "selection": {"mode": "undercovered-topics", "decision": "drop"},
            }
        ),
        encoding="utf-8",
    )
    nutrition_file = source_dir / "nutrition.json"
    nutrition_file.write_text(
        json.dumps(
            {
                "doi": "10.1000/nutrition",
                "title": "Nutrition paper",
                "selection": {"mode": "nutrition-rag", "decision": "drop"},
            }
        ),
        encoding="utf-8",
    )

    timestamp = 1775332800  # 2026-04-03 12:00:00 UTC
    os.utime(gap_file, (timestamp, timestamp))
    os.utime(nutrition_file, (timestamp, timestamp))
    target_date = datetime.fromtimestamp(timestamp).date().isoformat()

    manifest = MODULE.move_gap_rag_discards_for_date(
        source_dir=source_dir,
        target_date=target_date,
    )

    target_dir = source_dir / "gap-rag" / target_date
    assert manifest["moved_count"] == 1
    assert (target_dir / "gap.json").exists()
    assert not gap_file.exists()
    assert nutrition_file.exists()
    saved_manifest = json.loads((target_dir / "manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["moved_files"][0]["doi"] == "10.1000/gap"
