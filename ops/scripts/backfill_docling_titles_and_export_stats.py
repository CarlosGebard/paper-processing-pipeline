#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config_loader as ctx
from paper_pipeline.artifacts import load_registry, normalize_doi, slugify_doi
from paper_pipeline.docling_pipeline.title_resolution import (
    find_default_relations_csv,
    normalize_optional_text,
    resolve_docling_title,
    pdf_title_from_relation_row as relation_row_to_title,
)


def load_metadata_title_map(metadata_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in sorted(metadata_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        section = payload.get("metadata") if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else payload
        if not isinstance(section, dict):
            continue
        doi = str(section.get("doi") or "").strip()
        title = str(section.get("title") or "").strip()
        if doi and title:
            mapping[normalize_doi(doi)] = title
    return mapping


def pdf_title_from_relation_row(row: dict[str, str]) -> str:
    return normalize_optional_text(relation_row_to_title(row)) or ""


def load_relations_map(relations_csv: Path | None) -> dict[str, dict[str, str]]:
    if not relations_csv or not relations_csv.exists():
        return {}
    mapping: dict[str, dict[str, str]] = {}
    with relations_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            doi = normalize_optional_text(row.get("doi"))
            if doi:
                mapping[normalize_doi(doi)] = row
    return mapping


def build_relations_title_map(relations_map: dict[str, dict[str, str]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for doi, row in relations_map.items():
        title = pdf_title_from_relation_row(row)
        if title:
            mapping[slugify_doi(normalize_doi(doi))] = title
    return mapping


def count_nodes(sections: list[dict[str, Any]]) -> int:
    total = 0
    for section in sections:
        total += 1
        subsections = section.get("subsections", [])
        if isinstance(subsections, list):
            total += count_nodes(subsections)
    return total


def resolve_bundle_title(
    *,
    source: dict[str, Any] | None,
    relations_title_map: dict[str, str],
    existing_title: str | None = None,
) -> tuple[str | None, str]:
    return resolve_docling_title(
        source=source,
        metadata_dir=ctx.METADATA_DIR,
        relations_title_map=relations_title_map,
        existing_title=existing_title,
    )


def backfill_docling_titles(
    *,
    docling_dir: Path,
    metadata_titles: dict[str, str],
    relations_map: dict[str, dict[str, str]],
    dry_run: bool,
) -> dict[str, int]:
    stats = {
        "bundles_seen": 0,
        "filtered_updated": 0,
        "final_updated": 0,
        "title_missing": 0,
        "resolved_from_metadata": 0,
        "resolved_from_relations": 0,
        "resolved_from_existing": 0,
    }

    _ = metadata_titles
    relations_title_map = build_relations_title_map(relations_map)
    bundle_dirs = sorted(path for path in docling_dir.iterdir() if path.is_dir()) if docling_dir.exists() else []

    for bundle_dir in bundle_dirs:
        base_name = bundle_dir.name
        filtered_path = bundle_dir / f"{base_name}.filtered.json"
        final_path = bundle_dir / f"{base_name}.final.json"
        if not filtered_path.exists() and not final_path.exists():
            continue

        source_payload: dict[str, Any] = {"name": base_name}
        stats["bundles_seen"] += 1
        final_title: str | None = None
        if final_path.exists():
            try:
                final_payload = json.loads(final_path.read_text(encoding="utf-8"))
            except Exception:
                final_payload = {}
            paper = final_payload.get("paper") if isinstance(final_payload.get("paper"), dict) else {}
            final_title = normalize_optional_text(paper.get("title"))
        else:
            final_payload = {}

        if filtered_path.exists():
            try:
                filtered_payload_for_source = json.loads(filtered_path.read_text(encoding="utf-8"))
            except Exception:
                filtered_payload_for_source = {}
            source_candidate = filtered_payload_for_source.get("source")
            if isinstance(source_candidate, dict):
                source_payload = source_candidate

        resolved_title, source = resolve_bundle_title(
            source=source_payload,
            relations_title_map=relations_title_map,
            existing_title=final_title,
        )
        if source == "metadata":
            stats["resolved_from_metadata"] += 1
        elif source == "doi_pdf_relations":
            stats["resolved_from_relations"] += 1
        elif source == "existing":
            stats["resolved_from_existing"] += 1

        if not resolved_title:
            stats["title_missing"] += 1
            continue

        if filtered_path.exists():
            filtered_payload = json.loads(filtered_path.read_text(encoding="utf-8"))
            if filtered_payload.get("paper_title") != resolved_title:
                filtered_payload["paper_title"] = resolved_title
                if not dry_run:
                    filtered_path.write_text(json.dumps(filtered_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                stats["filtered_updated"] += 1

        if final_path.exists():
            final_payload = json.loads(final_path.read_text(encoding="utf-8"))
            paper = final_payload.get("paper") if isinstance(final_payload.get("paper"), dict) else {}
            if paper.get("title") != resolved_title:
                paper["title"] = resolved_title
                final_payload["paper"] = paper
                if not dry_run:
                    final_path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                stats["final_updated"] += 1

    return stats


def build_stats_rows(
    *,
    relations_map: dict[str, dict[str, str]],
    metadata_titles: dict[str, str],
    claims_dir: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    registry = load_registry()
    for doi, record in sorted(registry.items(), key=lambda item: item[0]):
        paths = record.get("paths") or {}
        stage_status = record.get("stage_status") or {}
        filtered_path = Path(str(paths.get("filtered_json") or ""))
        final_path = Path(str(paths.get("final_json") or ""))
        claims_path = Path(str(paths.get("claims") or "")) if paths.get("claims") else claims_dir / f"{record.get('base_name')}.claims.json"
        relation = relations_map.get(doi, {})

        filtered_payload = json.loads(filtered_path.read_text(encoding="utf-8")) if filtered_path.exists() else {}
        final_payload = json.loads(final_path.read_text(encoding="utf-8")) if final_path.exists() else {}
        claims_payload = json.loads(claims_path.read_text(encoding="utf-8")) if claims_path.exists() else []

        filtered_sections = filtered_payload.get("sections", []) if isinstance(filtered_payload, dict) else []
        final_sections = final_payload.get("sections", []) if isinstance(final_payload, dict) else []
        final_paper = final_payload.get("paper") if isinstance(final_payload, dict) and isinstance(final_payload.get("paper"), dict) else {}
        paper_title = (
            normalize_optional_text(filtered_payload.get("paper_title"))
            or normalize_optional_text(final_paper.get("title"))
            or normalize_optional_text(metadata_titles.get(doi))
            or ""
        )

        rows.append(
            {
                "base_name": str(record.get("base_name") or ""),
                "document_id": str(record.get("document_id") or ""),
                "doi": doi,
                "paper_title": paper_title,
                "metadata_title": metadata_titles.get(doi, ""),
                "relation_pdf_title": pdf_title_from_relation_row(relation) if relation else "",
                "relation_attachment_path_raw": relation.get("attachment_path_raw", ""),
                "relation_resolved_pdf_path": relation.get("resolved_pdf_path", ""),
                "metadata_exists": bool(stage_status.get("metadata")),
                "pdf_exists": bool(stage_status.get("pdf")),
                "docling_json_exists": Path(str(paths.get("docling_json") or "")).exists(),
                "filtered_json_exists": filtered_path.exists(),
                "final_json_exists": final_path.exists(),
                "claims_exists": claims_path.exists(),
                "filtered_top_level_sections": len(filtered_sections) if isinstance(filtered_sections, list) else 0,
                "filtered_total_sections": count_nodes(filtered_sections) if isinstance(filtered_sections, list) else 0,
                "final_top_level_sections": len(final_sections) if isinstance(final_sections, list) else 0,
                "final_total_sections": count_nodes(final_sections) if isinstance(final_sections, list) else 0,
                "claims_count": len(claims_payload) if isinstance(claims_payload, list) else 0,
                "registry_completed": bool(stage_status.get("completed")),
                "registry_heuristics": bool(stage_status.get("heuristics")),
                "registry_claims": bool(stage_status.get("claims")),
            }
        )
    return rows


def write_stats_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "base_name",
        "document_id",
        "doi",
        "paper_title",
        "metadata_title",
        "relation_pdf_title",
        "relation_attachment_path_raw",
        "relation_resolved_pdf_path",
        "metadata_exists",
        "pdf_exists",
        "docling_json_exists",
        "filtered_json_exists",
        "final_json_exists",
        "claims_exists",
        "filtered_top_level_sections",
        "filtered_total_sections",
        "final_top_level_sections",
        "final_total_sections",
        "claims_count",
        "registry_completed",
        "registry_heuristics",
        "registry_claims",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_stats_summary(rows: list[dict[str, Any]], backfill_stats: dict[str, int], output_csv: Path) -> None:
    total = len(rows)
    with_titles = sum(1 for row in rows if row["paper_title"])
    with_relations = sum(1 for row in rows if row["relation_attachment_path_raw"])
    with_filtered = sum(1 for row in rows if row["filtered_json_exists"])
    with_final = sum(1 for row in rows if row["final_json_exists"])
    with_claims = sum(1 for row in rows if row["claims_exists"])
    completed = sum(1 for row in rows if row["registry_completed"])
    filtered_sections = sum(int(row["filtered_total_sections"]) for row in rows)
    final_sections = sum(int(row["final_total_sections"]) for row in rows)
    claims_total = sum(int(row["claims_count"]) for row in rows)

    print("Docling title backfill + pipeline stats")
    print(f"- CSV: {ctx.display_path(output_csv)}")
    print(f"- Registry rows: {total}")
    print(f"- Rows with paper_title: {with_titles}")
    print(f"- Rows linked by doi_pdf_relations: {with_relations}")
    print(f"- Rows with filtered_json: {with_filtered}")
    print(f"- Rows with final_json: {with_final}")
    print(f"- Rows with claims: {with_claims}")
    print(f"- Registry completed: {completed}")
    print(f"- Total filtered sections: {filtered_sections}")
    print(f"- Total final sections: {final_sections}")
    print(f"- Total claims extracted: {claims_total}")
    print("Backfill")
    print(f"- Bundles seen: {backfill_stats['bundles_seen']}")
    print(f"- filtered.json updated: {backfill_stats['filtered_updated']}")
    print(f"- final.json updated: {backfill_stats['final_updated']}")
    print(f"- Titles resolved from metadata: {backfill_stats['resolved_from_metadata']}")
    print(f"- Titles resolved from doi_pdf_relations: {backfill_stats['resolved_from_relations']}")
    print(f"- Titles reused from existing final paper.title: {backfill_stats['resolved_from_existing']}")
    print(f"- Bundles still missing title: {backfill_stats['title_missing']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill paper_title into docling_heuristics bundles and export detailed pipeline stats CSV."
    )
    parser.add_argument("--metadata-dir", type=Path, default=ctx.METADATA_DIR)
    parser.add_argument("--docling-dir", type=Path, default=ctx.DOCLING_HEURISTICS_DIR)
    parser.add_argument("--claims-dir", type=Path, default=ctx.CLAIMS_OUTPUT_DIR)
    parser.add_argument("--relations-csv", type=Path, default=find_default_relations_csv())
    parser.add_argument("--output-csv", type=Path, default=ctx.DATA_DIR / "sources" / "pipeline_stats.csv")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx.ensure_dirs()

    metadata_titles = load_metadata_title_map(args.metadata_dir.expanduser().resolve())
    relations_map = load_relations_map(args.relations_csv.expanduser().resolve() if args.relations_csv else None)
    backfill_stats = backfill_docling_titles(
        docling_dir=args.docling_dir.expanduser().resolve(),
        metadata_titles=metadata_titles,
        relations_map=relations_map,
        dry_run=args.dry_run,
    )
    rows = build_stats_rows(
        relations_map=relations_map,
        metadata_titles=metadata_titles,
        claims_dir=args.claims_dir.expanduser().resolve(),
    )
    if not args.dry_run:
        write_stats_csv(rows, args.output_csv.expanduser().resolve())
    print_stats_summary(rows, backfill_stats, args.output_csv.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
