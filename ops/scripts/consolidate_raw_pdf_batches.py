#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config_loader as ctx
from paper_pipeline.tools.pdf_normalization import audit_raw_pdf_dir


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_conflict_target(target_dir: Path, source_name: str, source_label: str) -> Path:
    stem = Path(source_name).stem
    suffix = Path(source_name).suffix
    candidate = target_dir / f"{stem}__from-{source_label}{suffix}"
    index = 2
    while candidate.exists():
        candidate = target_dir / f"{stem}__from-{source_label}-{index}{suffix}"
        index += 1
    return candidate


def merge_raw_pdf_batches(
    source_dirs: list[Path],
    target_dir: Path,
    *,
    mode: str = "copy",
) -> dict[str, int]:
    target_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "copied": 0,
        "moved": 0,
        "duplicates": 0,
        "conflicts": 0,
        "missing_sources": 0,
    }

    for source_dir in source_dirs:
        if not source_dir.exists():
            print(f"[SOURCE MISSING] {source_dir}")
            stats["missing_sources"] += 1
            continue

        source_label = source_dir.name.replace("_", "-")
        for source_pdf in sorted(source_dir.glob("*.pdf")):
            target_path = target_dir / source_pdf.name
            if not target_path.exists():
                if mode == "move":
                    shutil.move(str(source_pdf), str(target_path))
                    stats["moved"] += 1
                else:
                    shutil.copy2(source_pdf, target_path)
                    stats["copied"] += 1
                continue

            if file_sha256(source_pdf) == file_sha256(target_path):
                print(f"[DUPLICATE] {source_pdf.name}")
                stats["duplicates"] += 1
                continue

            conflict_target = unique_conflict_target(target_dir, source_pdf.name, source_label)
            if mode == "move":
                shutil.move(str(source_pdf), str(conflict_target))
                stats["moved"] += 1
            else:
                shutil.copy2(source_pdf, conflict_target)
                stats["copied"] += 1

            print(f"[CONFLICT] {source_pdf.name} -> {conflict_target.name}")
            stats["conflicts"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge raw PDF batches from data/pdfs into the canonical raw PDF stage directory."
    )
    parser.add_argument(
        "--source-dir",
        dest="source_dirs",
        action="append",
        type=Path,
        help="Source batch directory. Can be passed multiple times.",
    )
    parser.add_argument("--target-dir", type=Path, default=ctx.RAW_PDF_DIR)
    parser.add_argument(
        "--mode",
        choices=("copy", "move"),
        default="copy",
        help="Copy by default. Use move only when you want to drain the source batches.",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=ctx.METADATA_DIR,
        help="Metadata directory used to audit DOI-first normalization readiness.",
    )
    parser.add_argument(
        "--bib-file",
        type=Path,
        default=ctx.BIB_OUTPUT_FILE,
        help="Optional .bib file used for DOI lookup during the audit report.",
    )
    args = parser.parse_args()

    default_sources = [
        ROOT_DIR / "data" / "pdfs" / "next_batch",
        ROOT_DIR / "data" / "pdfs" / "raw_pdf_2026-03-21",
    ]
    source_dirs = [path.expanduser().resolve() for path in (args.source_dirs or default_sources)]
    target_dir = args.target_dir.expanduser().resolve()

    stats = merge_raw_pdf_batches(source_dirs, target_dir, mode=args.mode)
    audit = audit_raw_pdf_dir(target_dir, args.metadata_dir.expanduser().resolve(), args.bib_file)

    print("Raw PDF batch consolidation completed")
    print(f"- Target dir: {target_dir}")
    print(f"- Files copied: {stats['copied']}")
    print(f"- Files moved: {stats['moved']}")
    print(f"- Identical duplicates skipped: {stats['duplicates']}")
    print(f"- Naming conflicts preserved separately: {stats['conflicts']}")
    print(f"- Missing source dirs: {stats['missing_sources']}")
    print("Normalization audit")
    print(f"- Total PDFs in raw: {audit['total']}")
    print(f"- Already DOI-first: {audit['already_doi']}")
    print(f"- Legacy DOI names: {audit['legacy']}")
    print(f"- Resolvable from metadata/bib: {audit['matched_from_lookup']}")
    print(f"- Unmatched: {audit['unmatched']}")
    if audit["unmatched_files"]:
        print("- Unmatched files:")
        for name in audit["unmatched_files"]:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
