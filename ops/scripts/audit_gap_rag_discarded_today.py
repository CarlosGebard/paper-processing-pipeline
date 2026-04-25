#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx


def _today_iso() -> str:
    return datetime.now().date().isoformat()


def build_target_dir(source_dir: Path, bucket_date: str) -> Path:
    return source_dir / "gap-rag" / bucket_date


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _is_gap_rag_discard(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    selection = payload.get("selection")
    if not isinstance(selection, dict):
        return False
    return str(selection.get("mode") or "").strip() in {"gap-rag", "undercovered-topics"}


def _was_modified_on(path: Path, expected_date: str) -> bool:
    modified_date = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    return modified_date == expected_date


def move_gap_rag_discards_for_date(
    *,
    source_dir: Path,
    target_date: str,
) -> dict[str, Any]:
    target_dir = build_target_dir(source_dir, target_date)
    target_dir.mkdir(parents=True, exist_ok=True)

    moved: list[dict[str, str]] = []
    skipped: list[str] = []

    for path in sorted(source_dir.glob("*.json")):
        payload = _load_json(path)
        if not _is_gap_rag_discard(payload):
            continue
        if not _was_modified_on(path, target_date):
            continue

        destination = target_dir / path.name
        if destination.exists():
            skipped.append(path.name)
            continue

        shutil.move(str(path), str(destination))
        moved.append(
            {
                "file_name": path.name,
                "doi": str((payload or {}).get("doi") or ""),
                "title": str((payload or {}).get("title") or ""),
            }
        )

    manifest = {
        "target_date": target_date,
        "source_dir": ctx.display_path(source_dir),
        "target_dir": ctx.display_path(target_dir),
        "moved_count": len(moved),
        "skipped_existing_count": len(skipped),
        "moved_files": moved,
        "skipped_existing": skipped,
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mueve los discarded papers de gap-rag modificados en una fecha dada "
            "desde el bucket legacy a una carpeta auditada por fecha."
        )
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=ctx.PATHS["discarded_dir"],
        help="Directorio legacy de discarded papers.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=_today_iso(),
        help="Fecha objetivo en formato YYYY-MM-DD. Default: hoy.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source_dir = args.source_dir.expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"No existe source_dir: {source_dir}")

    manifest = move_gap_rag_discards_for_date(
        source_dir=source_dir,
        target_date=str(args.date).strip(),
    )

    print("Gap-rag discarded audit")
    print(f"- source_dir:            {manifest['source_dir']}")
    print(f"- target_dir:            {manifest['target_dir']}")
    print(f"- target_date:           {manifest['target_date']}")
    print(f"- moved_count:           {manifest['moved_count']}")
    print(f"- skipped_existing:      {manifest['skipped_existing_count']}")
    for item in manifest["moved_files"][:10]:
        print(f"  - {item['file_name']} | doi={item['doi']} | title={item['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
