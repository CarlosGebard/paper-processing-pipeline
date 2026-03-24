#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config_loader as ctx
from paper_pipeline.artifacts import build_base_name, parse_base_name, upsert_registry_record


def unwrap_metadata(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
        return payload["metadata"]
    return payload if isinstance(payload, dict) else {}


def rename_path(source: Path, target: Path) -> bool:
    if source == target:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    return True


def migrate_metadata_files(metadata_dir: Path) -> tuple[int, int]:
    renamed = 0
    skipped = 0

    for path in sorted(metadata_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            skipped += 1
            continue

        metadata = unwrap_metadata(payload)
        doi = str(metadata.get("doi") or "").strip()
        if not doi:
            skipped += 1
            continue

        target = metadata_dir / f"{build_base_name(doi)}.metadata.json"
        if target.exists() and target != path:
            skipped += 1
            continue

        if rename_path(path, target):
            renamed += 1

    return renamed, skipped


def migrate_discarded_files(discarded_dir: Path) -> tuple[int, int]:
    renamed = 0
    skipped = 0
    if not discarded_dir.exists():
        return renamed, skipped

    for path in sorted(discarded_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            skipped += 1
            continue

        doi = str(payload.get("doi") or "").strip()
        if not doi:
            skipped += 1
            continue

        target = discarded_dir / f"{build_base_name(doi)}.json"
        if target.exists() and target != path:
            skipped += 1
            continue

        if rename_path(path, target):
            renamed += 1

    return renamed, skipped


def _target_base_name_for_path(path: Path) -> str | None:
    stem = path.name if path.is_dir() else path.stem
    if path.name.endswith(".claims.json"):
        stem = path.name[:-len(".claims.json")]

    parsed = parse_base_name(stem)
    if not parsed:
        return None

    return f"doi-{parsed['doi_slug']}"


def _recover_bundle_base_name(directory: Path) -> str | None:
    for candidate in sorted(directory.glob("*.final.json")):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        paper = payload.get("paper") if isinstance(payload, dict) else None
        doi = str((paper or {}).get("doi") or "").strip()
        if doi:
            return build_base_name(doi)
    return None


def migrate_flat_artifact_dir(directory: Path, suffix: str) -> tuple[int, int]:
    renamed = 0
    skipped = 0
    if not directory.exists():
        return renamed, skipped

    for path in sorted(directory.glob(f"*{suffix}")):
        target_base_name = _target_base_name_for_path(path)
        if not target_base_name:
            skipped += 1
            continue

        target = directory / f"{target_base_name}{suffix}"
        if target.exists() and target != path:
            skipped += 1
            continue

        if rename_path(path, target):
            renamed += 1

    return renamed, skipped


def migrate_docling_bundles(bundle_root: Path) -> tuple[int, int]:
    renamed = 0
    skipped = 0
    if not bundle_root.exists():
        return renamed, skipped

    for directory in sorted(path for path in bundle_root.iterdir() if path.is_dir()):
        target_base_name = _target_base_name_for_path(directory)
        recovered_base_name = _recover_bundle_base_name(directory)
        if recovered_base_name and recovered_base_name != directory.name:
            target_base_name = recovered_base_name
        elif not target_base_name:
            target_base_name = recovered_base_name
        if not target_base_name:
            skipped += 1
            continue

        target_dir = bundle_root / target_base_name
        if target_dir.exists() and target_dir != directory:
            skipped += 1
            continue

        for child in sorted(directory.iterdir()):
            target_child = child
            if child.is_file():
                target_child_name = child.name.replace(directory.name, target_base_name, 1)
                target_child = directory / target_child_name
                if target_child != child:
                    child.rename(target_child)
                    renamed += 1

        if rename_path(directory, target_dir):
            renamed += 1

    return renamed, skipped


def rebuild_registry(metadata_dir: Path) -> int:
    rebuilt = 0
    for path in sorted(metadata_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        metadata = unwrap_metadata(payload)
        doi = str(metadata.get("doi") or "").strip()
        if not doi:
            continue

        document_id = str(metadata.get("document_id") or metadata.get("paperId") or "")
        upsert_registry_record({"document_id": document_id, "doi": doi}, build_base_name(doi))
        rebuilt += 1

    return rebuilt


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate pipeline artifacts to DOI-first names.")
    parser.add_argument("--metadata-dir", type=Path, default=ctx.METADATA_DIR)
    parser.add_argument("--discarded-dir", type=Path, default=ctx.PATHS["discarded_dir"])
    parser.add_argument("--input-pdf-dir", type=Path, default=ctx.DOCLING_INPUT_DIR)
    parser.add_argument("--docling-dir", type=Path, default=ctx.DOCLING_HEURISTICS_DIR)
    parser.add_argument("--claims-dir", type=Path, default=ctx.CLAIMS_OUTPUT_DIR)
    args = parser.parse_args()

    ctx.ensure_dirs()

    metadata_renamed, metadata_skipped = migrate_metadata_files(args.metadata_dir)
    discarded_renamed, discarded_skipped = migrate_discarded_files(args.discarded_dir)
    pdf_renamed, pdf_skipped = migrate_flat_artifact_dir(args.input_pdf_dir, ".pdf")
    claims_renamed, claims_skipped = migrate_flat_artifact_dir(args.claims_dir, ".claims.json")
    bundles_renamed, bundles_skipped = migrate_docling_bundles(args.docling_dir)
    rebuilt = rebuild_registry(args.metadata_dir)

    print("Migration to DOI-first artifact names completed")
    print(f"- Metadata renamed: {metadata_renamed}")
    print(f"- Metadata skipped: {metadata_skipped}")
    print(f"- Discarded renamed:{discarded_renamed}")
    print(f"- Discarded skipped:{discarded_skipped}")
    print(f"- PDFs renamed:     {pdf_renamed}")
    print(f"- PDFs skipped:     {pdf_skipped}")
    print(f"- Bundles renamed:  {bundles_renamed}")
    print(f"- Bundles skipped:  {bundles_skipped}")
    print(f"- Claims renamed:   {claims_renamed}")
    print(f"- Claims skipped:   {claims_skipped}")
    print(f"- Registry rows:    {rebuilt}")


if __name__ == "__main__":
    main()
