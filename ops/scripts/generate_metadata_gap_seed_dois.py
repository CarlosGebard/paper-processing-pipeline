#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from analytics import paths as analytics_ctx
from src import config as ctx
from src.artifacts import normalize_doi
from src.tools.pre_ingestion_topics import normalize_text


DEFAULT_TOPICS_FILE = analytics_ctx.PRE_INGESTION_TOPICS_YAML
DEFAULT_OUTPUT_FILE = ctx.EXPLORATION_SEED_DOI_FILE
DEFAULT_MIN_CITATIONS = int((ctx.CONFIG.get("exploration") or {}).get("min_citations", 100))


def load_explored_dois(explored_dois_file: Path) -> set[str]:
    explored: set[str] = set()
    if not explored_dois_file.exists():
        return explored

    for raw_line in explored_dois_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        explored.add(normalize_doi(line))
    return explored


def load_gap_topics(topics_file: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(topics_file.read_text(encoding="utf-8")) or {}
    raw_topics = payload.get("topics")
    if not isinstance(raw_topics, list):
        raise ValueError(f"El archivo {topics_file} debe contener una lista 'topics'.")

    topics: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen_names:
            continue
        search_terms = item.get("search_terms") or []
        normalized_terms: list[str] = []
        seen_terms: set[str] = set()
        for raw_term in search_terms:
            normalized = normalize_text(str(raw_term).replace("_", " "))
            if not normalized or normalized in seen_terms:
                continue
            normalized_terms.append(normalized)
            seen_terms.add(normalized)
        if not normalized_terms:
            normalized_name = normalize_text(name.replace("_", " "))
            if normalized_name:
                normalized_terms.append(normalized_name)
        if not normalized_terms:
            continue
        topics.append({"name": name, "search_terms": normalized_terms})
        seen_names.add(name)

    if not topics:
        raise ValueError(f"No se encontraron topics utiles en {topics_file}.")
    return topics


def load_metadata_index(metadata_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for metadata_file in sorted(metadata_dir.glob("*.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        doi_raw = str(payload.get("doi") or "").strip()
        if not doi_raw:
            continue
        doi = normalize_doi(doi_raw)
        if doi:
            index[doi] = payload
    return index


def load_paper_rows(csv_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not csv_path.exists():
        return rows
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not isinstance(row, dict):
                continue
            rows.append({key: str(value or "") for key, value in row.items()})
    return rows


def _match_topics(text: str, topics: list[dict[str, Any]]) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    tokens = normalized.split()
    matched_topics: list[str] = []
    for topic in topics:
        for term in topic["search_terms"]:
            if " " in term:
                if term in normalized:
                    matched_topics.append(str(topic["name"]))
                    break
                continue
            if any(token.startswith(term) for token in tokens):
                matched_topics.append(str(topic["name"]))
                break
    return matched_topics


def _parse_citation_count(value: Any) -> int:
    try:
        return int(value) if value not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def collect_gap_seed_rows(
    *,
    papers_rows: list[dict[str, str]],
    unclassified_rows: list[dict[str, str]],
    metadata_index: dict[str, dict[str, Any]],
    explored_dois: set[str],
    topics: list[dict[str, Any]],
    min_citations: int,
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    unclassified_by_doi = {
        normalize_doi(row.get("doi", ""))
        for row in unclassified_rows
        if normalize_doi(row.get("doi", ""))
    }

    for source_name, source_rows in (("unclassified", unclassified_rows), ("papers", papers_rows)):
        for row in source_rows:
            doi = normalize_doi(row.get("doi", ""))
            if not doi or doi in explored_dois:
                continue

            metadata = metadata_index.get(doi, {})
            title = str(metadata.get("title") or row.get("title") or "").strip()
            abstract = str(metadata.get("abstract") or "").strip()
            citation_count = _parse_citation_count(metadata.get("citationCount"))
            if citation_count < min_citations:
                continue

            matched_topics = _match_topics(f"{title}\n{abstract}", topics)
            if not matched_topics:
                continue

            existing = rows.get(doi)
            is_unclassified = doi in unclassified_by_doi or source_name == "unclassified"
            score = (len(matched_topics) * 100000) + (25000 if is_unclassified else 0) + citation_count

            candidate = {
                "doi": doi,
                "title": title,
                "citation_count": citation_count,
                "matched_topics": matched_topics,
                "source_bucket": "unclassified" if is_unclassified else source_name,
                "score": score,
            }

            if existing is None or candidate["score"] > existing["score"]:
                rows[doi] = candidate

    ordered = sorted(
        rows.values(),
        key=lambda item: (-item["score"], -item["citation_count"], item["title"].lower(), item["doi"]),
    )
    return ordered


def write_doi_output(rows: list[dict[str, Any]], output_path: Path, *, limit: int | None = None) -> int:
    selected_rows = rows[:limit] if limit is not None else rows
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(str(row["doi"]) for row in selected_rows)
    if selected_rows:
        content += "\n"
    output_path.write_text(content, encoding="utf-8")
    return len(selected_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Genera un seed_dois.txt priorizando gaps tematicos detectados en pre-ingestion "
            "a partir de papers.csv, audit/unclassified_papers.csv y metadata local."
        )
    )
    parser.add_argument(
        "--papers-csv",
        type=Path,
        default=analytics_ctx.PRE_INGESTION_PAPERS_CSV,
        help="CSV base del workspace pre-ingestion.",
    )
    parser.add_argument(
        "--unclassified-csv",
        type=Path,
        default=analytics_ctx.PRE_INGESTION_AUDIT_DIR / "unclassified_papers.csv",
        help="CSV de papers no clasificados del audit para priorizar.",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=ctx.METADATA_DIR,
        help="Directorio de metadata canonica local.",
    )
    parser.add_argument(
        "--explored-dois",
        type=Path,
        default=ctx.EXPLORATION_COMPLETED_SEED_DOI_FILE,
        help="Archivo txt con DOIs ya explorados para excluir.",
    )
    parser.add_argument(
        "--topics-file",
        type=Path,
        default=DEFAULT_TOPICS_FILE,
        help="YAML editable con gaps tematicos y terminos asociados.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Txt output con un DOI por linea.",
    )
    parser.add_argument(
        "--min-citations",
        type=int,
        default=DEFAULT_MIN_CITATIONS,
        help="Citas minimas requeridas para exportar un DOI.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Cantidad maxima de DOIs a escribir.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    papers_csv = args.papers_csv.expanduser().resolve()
    unclassified_csv = args.unclassified_csv.expanduser().resolve()
    metadata_dir = args.metadata_dir.expanduser().resolve()
    explored_dois_file = args.explored_dois.expanduser().resolve()
    topics_file = args.topics_file.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not papers_csv.exists():
        raise SystemExit(f"No existe papers_csv: {papers_csv}")
    if not metadata_dir.exists():
        raise SystemExit(f"No existe metadata_dir: {metadata_dir}")
    if not topics_file.exists():
        raise SystemExit(f"No existe topics_file: {topics_file}")

    topics = load_gap_topics(topics_file)
    metadata_index = load_metadata_index(metadata_dir)
    explored_dois = load_explored_dois(explored_dois_file)
    papers_rows = load_paper_rows(papers_csv)
    unclassified_rows = load_paper_rows(unclassified_csv)
    rows = collect_gap_seed_rows(
        papers_rows=papers_rows,
        unclassified_rows=unclassified_rows,
        metadata_index=metadata_index,
        explored_dois=explored_dois,
        topics=topics,
        min_citations=max(0, int(args.min_citations)),
    )
    written = write_doi_output(rows, output_path, limit=max(0, int(args.limit)))

    print("Metadata gap seed DOI candidates")
    print(f"- papers_csv:        {ctx.display_path(papers_csv)}")
    print(f"- unclassified_csv:  {ctx.display_path(unclassified_csv)}")
    print(f"- metadata_dir:      {ctx.display_path(metadata_dir)}")
    print(f"- explored_dois:     {ctx.display_path(explored_dois_file)}")
    print(f"- topics_file:       {ctx.display_path(topics_file)}")
    print(f"- output:            {ctx.display_path(output_path)}")
    print(f"- min_citations:     {max(0, int(args.min_citations))}")
    print(f"- topics_loaded:     {len(topics)}")
    print(f"- candidates_found:  {len(rows)}")
    print(f"- dois_written:      {written}")
    for row in rows[:10]:
        print(
            f"  - {row['doi']} | citations={row['citation_count']} | "
            f"bucket={row['source_bucket']} | matched={', '.join(row['matched_topics'][:3])} | title={row['title']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
