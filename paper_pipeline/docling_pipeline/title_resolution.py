from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import config_loader as ctx
from paper_pipeline.artifacts import metadata_path_for_base_name, normalize_doi, parse_base_name, slugify_doi
from paper_pipeline.tools.pdf_normalization import _extract_title_hint


def normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower() in {"none", "null", "nan"}:
        return None
    return text


def extract_source_base_name(source: dict[str, Any] | None) -> str | None:
    if not isinstance(source, dict):
        return None

    source_name = str(source.get("name", "")).strip()
    if not source_name:
        return None

    path = Path(source_name)
    if path.suffix.lower() == ".pdf":
        return path.stem or None
    return path.name or None


def extract_doi_slug_from_base_name(base_name: str | None) -> str | None:
    if not base_name:
        return None
    parsed = parse_base_name(base_name)
    if not parsed:
        return None
    return parsed.get("doi_slug")


def find_default_relations_csv() -> Path | None:
    candidates = sorted((ctx.DATA_DIR / "sources").glob("doi_pdf_relations*.csv"))
    return candidates[-1] if candidates else None


def load_metadata(source: dict[str, Any] | None, metadata_dir: Path | None = None) -> dict[str, Any]:
    base_name = extract_source_base_name(source)
    if not base_name or metadata_dir is None:
        return {}

    metadata_path = metadata_path_for_base_name(base_name, metadata_dir=metadata_dir)
    if metadata_path is None:
        return {}

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
        return payload["metadata"]
    if isinstance(payload, dict):
        return payload
    return {}


def pdf_title_from_relation_row(row: dict[str, str]) -> str | None:
    raw = (row.get("attachment_path_raw") or "").strip()
    if raw.startswith("storage:"):
        raw = raw[len("storage:") :]
    stem = Path(raw).stem.strip()
    title = normalize_optional_text(_extract_title_hint(stem))
    return title


def load_relations_title_map(relations_csv: Path | None) -> dict[str, str]:
    if not relations_csv or not relations_csv.exists():
        return {}

    mapping: dict[str, str] = {}
    with relations_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            doi = normalize_optional_text(row.get("doi"))
            title = pdf_title_from_relation_row(row)
            if not doi or not title:
                continue
            mapping[slugify_doi(normalize_doi(doi))] = title
    return mapping


def resolve_docling_title(
    *,
    source: dict[str, Any] | None,
    metadata_dir: Path | None = None,
    relations_title_map: dict[str, str] | None = None,
    existing_title: str | None = None,
) -> tuple[str | None, str]:
    normalized_existing = normalize_optional_text(existing_title)
    if normalized_existing:
        return normalized_existing, "existing"

    metadata = load_metadata(source, metadata_dir=metadata_dir)
    metadata_title = normalize_optional_text(metadata.get("title"))
    if metadata_title:
        return metadata_title, "metadata"

    base_name = extract_source_base_name(source)
    doi_slug = extract_doi_slug_from_base_name(base_name)
    if doi_slug and relations_title_map:
        relation_title = normalize_optional_text(relations_title_map.get(doi_slug))
        if relation_title:
            return relation_title, "doi_pdf_relations"

    return None, "missing"
