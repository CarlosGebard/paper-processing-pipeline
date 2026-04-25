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

from src import config as ctx
from src.artifacts import normalize_doi
from src.tools.pre_ingestion_topics import normalize_text


DEFAULT_TERMS_FILE = ctx.DATA_SOURCES_DIR / "metadata_seed_dictionary.txt"
DEFAULT_OUTPUT_FILE = ctx.DATA_SOURCES_DIR / "generated_seed_dois.txt"
DEFAULT_MIN_CITATIONS = int((ctx.CONFIG.get("exploration") or {}).get("min_citations", 100))


def metadata_section(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    section = payload.get("metadata")
    if isinstance(section, dict):
        return section
    return payload


def load_keyword_dictionary(terms_file: Path) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()

    for raw_line in terms_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = normalize_text(line)
        if not normalized or normalized in seen:
            continue
        keywords.append(normalized)
        seen.add(normalized)

    if not keywords:
        raise ValueError(f"No se encontraron keywords utiles en {terms_file}.")
    return keywords


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


def find_matching_keywords(text: str, keywords: list[str]) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    tokens = normalized.split()
    matched: list[str] = []

    for keyword in keywords:
        if " " in keyword:
            if keyword in normalized:
                matched.append(keyword)
            continue
        if any(token.startswith(keyword) for token in tokens):
            matched.append(keyword)

    return matched


def _parse_citation_count(value: Any) -> int:
    try:
        return int(value) if value not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def collect_candidate_rows(
    metadata_dir: Path,
    *,
    explored_dois: set[str],
    keywords: list[str],
    min_citations: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for metadata_file in sorted(metadata_dir.glob("*.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        section = metadata_section(payload)
        if not section:
            continue

        doi_raw = str(section.get("doi") or "").strip()
        title = str(section.get("title") or "").strip()
        abstract = str(section.get("abstract") or "").strip()
        if not doi_raw or not title:
            continue

        doi = normalize_doi(doi_raw)
        if doi in explored_dois:
            continue

        citation_count = _parse_citation_count(section.get("citationCount"))
        if citation_count < min_citations:
            continue

        matched_keywords = find_matching_keywords(f"{title}\n{abstract}", keywords)
        if not matched_keywords:
            continue

        rows.append(
            {
                "doi": doi,
                "title": title,
                "citation_count": citation_count,
                "matched_keywords": matched_keywords,
            }
        )

    rows.sort(key=lambda item: (-item["citation_count"], item["title"].lower(), item["doi"]))
    return rows


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
            "Genera un txt con DOIs candidatos para metadata retrieval "
            "usando metadata local, un diccionario editable de keywords "
            "y exclusion de explored_seed_dois.txt."
        )
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
        "--terms-file",
        type=Path,
        default=DEFAULT_TERMS_FILE,
        help="Archivo txt editable con keywords o raices, una por linea.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Txt output con un DOI por linea, ordenado por citationCount desc.",
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
    metadata_dir = args.metadata_dir.expanduser().resolve()
    explored_dois_file = args.explored_dois.expanduser().resolve()
    terms_file = args.terms_file.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not metadata_dir.exists():
        raise SystemExit(f"No existe metadata_dir: {metadata_dir}")
    if not terms_file.exists():
        raise SystemExit(f"No existe terms_file: {terms_file}")

    keywords = load_keyword_dictionary(terms_file)
    explored_dois = load_explored_dois(explored_dois_file)
    rows = collect_candidate_rows(
        metadata_dir,
        explored_dois=explored_dois,
        keywords=keywords,
        min_citations=max(0, int(args.min_citations)),
    )
    written = write_doi_output(rows, output_path, limit=max(0, int(args.limit)))

    print("Metadata seed DOI candidates")
    print(f"- metadata_dir:     {ctx.display_path(metadata_dir)}")
    print(f"- explored_dois:    {ctx.display_path(explored_dois_file)}")
    print(f"- terms_file:       {ctx.display_path(terms_file)}")
    print(f"- output:           {ctx.display_path(output_path)}")
    print(f"- min_citations:    {max(0, int(args.min_citations))}")
    print(f"- keywords_loaded:  {len(keywords)}")
    print(f"- candidates_found: {len(rows)}")
    print(f"- dois_written:     {written}")
    for row in rows[:10]:
        print(
            f"  - {row['doi']} | citations={row['citation_count']} | "
            f"matched={', '.join(row['matched_keywords'][:3])} | title={row['title']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
