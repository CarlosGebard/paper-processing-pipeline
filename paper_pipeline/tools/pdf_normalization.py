#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from paper_pipeline.artifacts import build_base_name, normalize_doi, parse_base_name


def _normalize_text_for_match(value: str) -> str:
    lowered = value.lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    compact = re.sub(r"[^a-z0-9]+", "", ascii_only)
    return compact


def _extract_title_hint(value: str) -> str:
    match = re.search(r"\s-\s\d{4}\s-\s(.+)$", value)
    if match:
        return match.group(1).strip()
    return value.strip()


def _iter_metadata_records(metadata_dir: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    if not metadata_dir.exists():
        return records

    for metadata_file in sorted(metadata_dir.glob("*.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        section = payload.get("metadata") if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else payload
        if not isinstance(section, dict):
            continue

        document_id = section.get("document_id") or section.get("paperId")
        doi = section.get("doi")
        title = section.get("title")
        citation_count = section.get("citationCount")
        if not doi or not title:
            continue

        title_key = _normalize_text_for_match(str(title))
        if not title_key:
            continue

        record_doi = normalize_doi(str(doi))
        records.append(
            {
                "document_id": str(document_id or ""),
                "doi": record_doi,
                "title_key": title_key,
                "base_name": build_base_name(record_doi),
                "citation_count": str(citation_count if citation_count is not None else ""),
            }
        )

    return records


def _extract_bib_field(entry_body: str, field_name: str) -> str | None:
    marker_match = re.search(rf"\b{re.escape(field_name)}\s*=", entry_body, flags=re.IGNORECASE)
    if not marker_match:
        return None

    i = marker_match.end()
    n = len(entry_body)
    while i < n and entry_body[i].isspace():
        i += 1
    if i >= n:
        return None

    if entry_body[i] == "{":
        depth = 0
        start = i + 1
        i += 1
        while i < n:
            ch = entry_body[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth == 0:
                    return entry_body[start:i].strip()
                depth -= 1
            i += 1
        return None

    if entry_body[i] == '"':
        start = i + 1
        i += 1
        while i < n:
            ch = entry_body[i]
            if ch == '"' and entry_body[i - 1] != "\\":
                return entry_body[start:i].strip()
            i += 1
        return None

    start = i
    while i < n and entry_body[i] not in ",\n":
        i += 1
    return entry_body[start:i].strip() or None


def _iter_bib_records(bib_file: Path | None) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    if not bib_file or not bib_file.exists():
        return records

    text = bib_file.read_text(encoding="utf-8", errors="ignore")
    for entry in re.finditer(r"@\w+\s*\{[^,]+,(?P<body>.*?)\n\}", text, flags=re.IGNORECASE | re.DOTALL):
        body = entry.group("body")
        title = _extract_bib_field(body, "title")
        doi = _extract_bib_field(body, "doi")
        if not title or not doi:
            continue

        title_key = _normalize_text_for_match(title)
        if not title_key:
            continue

        records.append({"title_key": title_key, "doi": normalize_doi(doi)})

    return records


def _default_relations_csv_from_metadata_dir(metadata_dir: Path) -> Path | None:
    source_dir = metadata_dir.parent if metadata_dir.name == "metadata" else metadata_dir
    candidates = sorted(source_dir.glob("doi_pdf_relations*.csv"))
    return candidates[0] if candidates else None


def _iter_relation_records(relations_csv: Path | None) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    if not relations_csv or not relations_csv.exists():
        return records

    with relations_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            doi = str(row.get("doi") or "").strip()
            attachment_path_raw = str(row.get("attachment_path_raw") or "").strip()
            resolved_pdf_path = str(row.get("resolved_pdf_path") or "").strip()
            if not doi:
                continue

            title_candidates = []
            if attachment_path_raw:
                if attachment_path_raw.startswith("storage:"):
                    attachment_path_raw = attachment_path_raw[len("storage:") :]
                title_candidates.append(Path(attachment_path_raw).stem)
            if resolved_pdf_path:
                title_candidates.append(Path(resolved_pdf_path).stem)

            for title_candidate in title_candidates:
                title_key = _normalize_text_for_match(_extract_title_hint(title_candidate))
                if not title_key:
                    continue
                records.append(
                    {
                        "title_key": title_key,
                        "doi": normalize_doi(doi),
                        "base_name": build_base_name(doi),
                    }
                )

    return records


def _extract_doi_from_text(text: str) -> str | None:
    match = re.search(r"(10\.\d{4,9}/[-._;()/:a-z0-9]+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return normalize_doi(match.group(1).rstrip(".,;:_-"))


def _pick_exact_unique(stem_key: str, records: list[dict[str, str]]) -> str | None:
    matches = {item["base_name"] for item in records if item["title_key"] == stem_key}
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _pick_exact_preferred_by_metadata(
    stem_key: str,
    records: list[dict[str, str]],
    metadata_records: list[dict[str, str]],
) -> str | None:
    matches = {item["base_name"] for item in records if item["title_key"] == stem_key}
    if len(matches) <= 1:
        return next(iter(matches)) if matches else None
    return _pick_preferred_base_name(matches, metadata_records)


def _pick_partial_best(stem_key: str, records: list[dict[str, str]]) -> str | None:
    scored: dict[str, int] = {}
    for item in records:
        title_key = item["title_key"]
        if len(title_key) < 24:
            continue
        if title_key in stem_key or stem_key in title_key:
            score = min(len(stem_key), len(title_key))
            best = scored.get(item["base_name"])
            if best is None or score > best:
                scored[item["base_name"]] = score

    if not scored:
        return None

    ordered = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    if len(ordered) == 1:
        return ordered[0][0]
    if ordered[0][1] >= ordered[1][1] + 8:
        return ordered[0][0]
    return None


def _pick_partial_preferred_by_metadata(
    stem_key: str,
    records: list[dict[str, str]],
    metadata_records: list[dict[str, str]],
) -> str | None:
    scored: dict[str, int] = {}
    for item in records:
        title_key = item["title_key"]
        if len(title_key) < 24:
            continue
        if title_key in stem_key or stem_key in title_key:
            score = min(len(stem_key), len(title_key))
            best = scored.get(item["base_name"])
            if best is None or score > best:
                scored[item["base_name"]] = score

    if not scored:
        return None

    ordered = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    if len(ordered) == 1:
        return ordered[0][0]
    if ordered[0][1] >= ordered[1][1] + 8:
        return ordered[0][0]

    top_score = ordered[0][1]
    top_candidates = {base_name for base_name, score in ordered if score == top_score}
    return _pick_preferred_base_name(top_candidates, metadata_records)


def _pick_preferred_base_name(
    candidate_base_names: set[str],
    metadata_records: list[dict[str, str]],
) -> str | None:
    if not candidate_base_names:
        return None

    citation_by_base: dict[str, int] = {}
    for record in metadata_records:
        base_name = record["base_name"]
        if base_name not in candidate_base_names:
            continue
        raw_citation = str(record.get("citation_count") or "").strip()
        try:
            citation_count = int(raw_citation) if raw_citation else -1
        except ValueError:
            citation_count = -1
        citation_by_base[base_name] = citation_count

    if not citation_by_base:
        return None

    ordered = sorted(citation_by_base.items(), key=lambda item: item[1], reverse=True)
    if len(ordered) == 1:
        return ordered[0][0]
    if ordered[0][1] > ordered[1][1]:
        return ordered[0][0]
    return None


def _guess_base_name_from_stem(
    stem: str,
    metadata_records: list[dict[str, str]],
    bib_records: list[dict[str, str]],
    relation_records: list[dict[str, str]] | None = None,
) -> str | None:
    stem_title_hint = _extract_title_hint(stem)
    stem_key = _normalize_text_for_match(stem_title_hint)
    if not stem_key:
        return None

    metadata_by_doi = {item["doi"]: item for item in metadata_records}
    stem_doi = _extract_doi_from_text(stem)
    if stem_doi and stem_doi in metadata_by_doi:
        return metadata_by_doi[stem_doi]["base_name"]

    bib_mapped_records: list[dict[str, str]] = []
    for bib_item in bib_records:
        mapped = metadata_by_doi.get(bib_item["doi"])
        if not mapped:
            continue
        bib_mapped_records.append({"title_key": bib_item["title_key"], "base_name": mapped["base_name"]})

    if bib_mapped_records:
        exact_bib = _pick_exact_preferred_by_metadata(stem_key, bib_mapped_records, metadata_records)
        if exact_bib:
            return exact_bib
        partial_bib = _pick_partial_preferred_by_metadata(stem_key, bib_mapped_records, metadata_records)
        if partial_bib:
            return partial_bib

    if relation_records:
        exact_relation = _pick_exact_preferred_by_metadata(stem_key, relation_records, metadata_records)
        if exact_relation:
            return exact_relation
        partial_relation = _pick_partial_preferred_by_metadata(stem_key, relation_records, metadata_records)
        if partial_relation:
            return partial_relation

    exact_meta = _pick_exact_preferred_by_metadata(stem_key, metadata_records, metadata_records)
    if exact_meta:
        return exact_meta
    partial_meta = _pick_partial_preferred_by_metadata(stem_key, metadata_records, metadata_records)
    if partial_meta:
        return partial_meta

    return None


def resolve_pdf_target_name(
    source_pdf: Path,
    metadata_records: list[dict[str, str]],
    bib_records: list[dict[str, str]],
    relation_records: list[dict[str, str]] | None = None,
) -> str | None:
    stem = source_pdf.stem
    parsed = parse_base_name(stem)
    if parsed:
        return source_pdf.name if parsed["format"] == "doi" else f"doi-{parsed['doi_slug']}.pdf"

    guessed_base_name = _guess_base_name_from_stem(stem, metadata_records, bib_records, relation_records)
    if guessed_base_name:
        return f"{guessed_base_name}.pdf"

    return None


def audit_raw_pdf_dir(
    raw_pdf_dir: Path,
    metadata_dir: Path,
    bib_file: Path | None = None,
    relations_csv: Path | None = None,
) -> dict[str, Any]:
    metadata_records = _iter_metadata_records(metadata_dir)
    bib_records = _iter_bib_records(bib_file)
    relation_records = _iter_relation_records(relations_csv or _default_relations_csv_from_metadata_dir(metadata_dir))

    summary: dict[str, Any] = {
        "total": 0,
        "already_doi": 0,
        "legacy": 0,
        "matched_from_lookup": 0,
        "unmatched": 0,
        "unmatched_files": [],
    }
    if not raw_pdf_dir.exists():
        return summary

    for source_pdf in sorted(raw_pdf_dir.glob("*.pdf")):
        summary["total"] += 1
        parsed = parse_base_name(source_pdf.stem)
        if parsed:
            if parsed["format"] == "doi":
                summary["already_doi"] += 1
            else:
                summary["legacy"] += 1
            continue

        target_name = resolve_pdf_target_name(source_pdf, metadata_records, bib_records, relation_records)
        if target_name:
            summary["matched_from_lookup"] += 1
            continue

        summary["unmatched"] += 1
        summary["unmatched_files"].append(source_pdf.name)

    return summary


def sync_raw_pdfs_into_input(
    raw_pdf_dir: Path,
    input_dir: Path,
    metadata_dir: Path,
    bib_file: Path | None = None,
    relations_csv: Path | None = None,
) -> tuple[int, int]:
    if not raw_pdf_dir.exists():
        return 0, 0

    input_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0

    metadata_records = _iter_metadata_records(metadata_dir)
    bib_records = _iter_bib_records(bib_file)
    relation_records = _iter_relation_records(relations_csv or _default_relations_csv_from_metadata_dir(metadata_dir))

    for source_pdf in sorted(raw_pdf_dir.glob("*.pdf")):
        target_name = resolve_pdf_target_name(source_pdf, metadata_records, bib_records, relation_records)

        if not target_name:
            print(f"[RAW SKIP] {source_pdf.name}: no se pudo inferir doi (bib+metadata)")
            skipped += 1
            continue

        target_path = input_dir / target_name
        shutil.copy2(source_pdf, target_path)
        copied += 1

    return copied, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normaliza PDFs desde data/raw_pdf al formato trazable en data/input_pdfs"
    )
    parser.add_argument("--raw-dir", type=Path, required=True, help="Directorio fuente de PDFs crudos")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directorio destino normalizado")
    parser.add_argument("--metadata-dir", type=Path, required=True, help="Directorio con metadata JSON para matching")
    parser.add_argument("--bib-file", type=Path, default=None, help="Archivo .bib opcional para priorizar matching")
    parser.add_argument("--relations-csv", type=Path, default=None, help="CSV opcional doi_pdf_relations para fallback de DOI")
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Solo reporta si los PDFs crudos ya pueden resolverse a DOI-first, sin copiar archivos",
    )
    args = parser.parse_args()

    if args.audit_only:
        summary = audit_raw_pdf_dir(args.raw_dir, args.metadata_dir, args.bib_file, args.relations_csv)
        print("Auditoria raw_pdf -> input_pdfs")
        print(f"- Total PDFs: {summary['total']}")
        print(f"- Ya DOI: {summary['already_doi']}")
        print(f"- Legacy: {summary['legacy']}")
        print(f"- Matched via metadata/bib: {summary['matched_from_lookup']}")
        print(f"- Sin DOI resoluble: {summary['unmatched']}")
        return

    copied, skipped = sync_raw_pdfs_into_input(args.raw_dir, args.input_dir, args.metadata_dir, args.bib_file, args.relations_csv)
    print("Sincronizacion raw_pdf -> input_pdfs")
    print(f"- Copiados: {copied}")
    print(f"- Omitidos: {skipped}")


if __name__ == "__main__":
    main()
