#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata
from pathlib import Path


def normalize_doi(doi: str) -> str:
    value = doi.strip()
    value = re.sub(r"^https?://(dx\\.)?doi\\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    return value.strip().lower()


def slugify_doi(doi: str) -> str:
    normalized = normalize_doi(doi)
    slug = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown-doi"


def build_base_name(document_id: str, doi: str) -> str:
    return f"{document_id}__doi-{slugify_doi(doi)}"


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
        if not document_id or not doi or not title:
            continue

        title_key = _normalize_text_for_match(str(title))
        if not title_key:
            continue

        record_doi = normalize_doi(str(doi))
        records.append(
            {
                "document_id": str(document_id),
                "doi": record_doi,
                "title_key": title_key,
                "base_name": build_base_name(str(document_id), record_doi),
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


def _guess_base_name_from_stem(
    stem: str,
    metadata_records: list[dict[str, str]],
    bib_records: list[dict[str, str]],
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
        exact_bib = _pick_exact_unique(stem_key, bib_mapped_records)
        if exact_bib:
            return exact_bib
        partial_bib = _pick_partial_best(stem_key, bib_mapped_records)
        if partial_bib:
            return partial_bib

    exact_meta = _pick_exact_unique(stem_key, metadata_records)
    if exact_meta:
        return exact_meta
    partial_meta = _pick_partial_best(stem_key, metadata_records)
    if partial_meta:
        return partial_meta

    return None


def sync_raw_pdfs_into_input(
    raw_pdf_dir: Path,
    input_dir: Path,
    metadata_dir: Path,
    bib_file: Path | None = None,
) -> tuple[int, int]:
    if not raw_pdf_dir.exists():
        return 0, 0

    input_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0

    metadata_records = _iter_metadata_records(metadata_dir)
    bib_records = _iter_bib_records(bib_file)

    for source_pdf in sorted(raw_pdf_dir.glob("*.pdf")):
        stem = source_pdf.stem
        match = re.match(r"^(?P<docid>[^_]+)__doi-(?P<doi_slug>.+)$", stem)

        target_name: str | None = None
        if match:
            target_name = source_pdf.name
        else:
            guessed_base_name = _guess_base_name_from_stem(stem, metadata_records, bib_records)
            if guessed_base_name:
                target_name = f"{guessed_base_name}.pdf"

        if not target_name:
            print(f"[RAW SKIP] {source_pdf.name}: no se pudo inferir document_id/doi (bib+metadata)")
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
    args = parser.parse_args()

    copied, skipped = sync_raw_pdfs_into_input(args.raw_dir, args.input_dir, args.metadata_dir, args.bib_file)
    print("Sincronizacion raw_pdf -> input_pdfs")
    print(f"- Copiados: {copied}")
    print(f"- Omitidos: {skipped}")


if __name__ == "__main__":
    main()
