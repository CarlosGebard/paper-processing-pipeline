from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config_loader as ctx


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def trace_block(document_id: str, doi: str) -> dict[str, str]:
    return {
        "document_id": document_id,
        "doi": normalize_doi(doi),
        "created_at": utc_now_iso(),
    }


def load_registry() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not ctx.REGISTRY_FILE.exists():
        return records

    for line in ctx.REGISTRY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        records[data["document_id"]] = data

    return records


def save_registry(records: dict[str, dict[str, Any]]) -> None:
    lines = [json.dumps(records[document_id], ensure_ascii=False) for document_id in sorted(records.keys())]
    ctx.REGISTRY_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def artifact_paths_for_base_name(base_name: str) -> dict[str, Path]:
    bundle_dir = ctx.DOCLING_HEURISTICS_DIR / base_name
    return {
        "metadata": ctx.METADATA_DIR / f"{base_name}.metadata.json",
        "pdf": ctx.DOCLING_INPUT_DIR / f"{base_name}.pdf",
        "docling_heuristics_dir": bundle_dir,
        "docling_json": bundle_dir / f"{base_name}.json",
        "filtered_json": bundle_dir / f"{base_name}.filtered.json",
        "final_json": bundle_dir / f"{base_name}.final.json",
        "claims": ctx.CLAIMS_OUTPUT_DIR / f"{base_name}.claims.json",
    }


def metadata_exists_for_base_name(base_name: str) -> bool:
    default_path = ctx.METADATA_DIR / f"{base_name}.metadata.json"
    if default_path.exists():
        return True

    document_id = base_name.split("__doi-", 1)[0]
    legacy_path = ctx.METADATA_DIR / f"{document_id}.json"
    return legacy_path.exists()


def artifact_stage_status(paths: dict[str, Path]) -> dict[str, bool]:
    return {
        "metadata": metadata_exists_for_base_name(paths["metadata"].stem.replace(".metadata", "")),
        "pdf": paths["pdf"].exists(),
        "docling": paths["docling_json"].exists(),
        "heuristics": paths["filtered_json"].exists() and paths["final_json"].exists(),
        "claims": paths["claims"].exists(),
        "completed": (
            paths["docling_json"].exists()
            and paths["filtered_json"].exists()
            and paths["final_json"].exists()
            and paths["claims"].exists()
        ),
    }


def upsert_registry_record(metadata: dict[str, Any], base_name: str) -> dict[str, Any]:
    records = load_registry()

    document_id = metadata["document_id"]
    entry = records.get(document_id, {})
    artifact_paths = artifact_paths_for_base_name(base_name)
    entry.update(
        {
            "document_id": document_id,
            "doi": metadata["doi"],
            "base_name": base_name,
            "updated_at": utc_now_iso(),
            "paths": {name: str(path) for name, path in artifact_paths.items()},
            "stage_status": artifact_stage_status(artifact_paths),
        }
    )

    records[document_id] = entry
    save_registry(records)
    return entry


def refresh_registry_record(document_id: str, doi: str, base_name: str) -> dict[str, Any]:
    return upsert_registry_record({"document_id": document_id, "doi": doi}, base_name)


def _metadata_section(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    section = payload.get("metadata")
    if isinstance(section, dict):
        return section
    return payload


def _iter_metadata_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if not ctx.METADATA_DIR.exists():
        return entries

    for metadata_file in sorted(ctx.METADATA_DIR.glob("*.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        section = _metadata_section(payload)
        if not section:
            continue

        document_id = section.get("document_id") or section.get("paperId")
        doi = section.get("doi")
        if not document_id or not doi:
            continue

        entries.append({"document_id": str(document_id), "doi": normalize_doi(str(doi))})

    return entries


def _resolve_metadata_for_pdf(document_id: str, doi_slug: str) -> dict[str, str] | None:
    entries = _iter_metadata_entries()

    for entry in entries:
        if entry["document_id"] == document_id:
            return entry

    for entry in entries:
        if slugify_doi(entry["doi"]) == doi_slug:
            return entry

    return None


def parse_document_from_pdf_name(pdf_path: Path) -> tuple[str, str, str]:
    match = re.match(r"^(?P<docid>[^_]+)__doi-(?P<doi_slug>.+)$", pdf_path.stem)
    if not match:
        raise RuntimeError(
            f"PDF no cumple convencion '<document_id>__doi-<doi_slug>.pdf': {pdf_path.name}"
        )

    doc_id = match.group("docid")
    doi_slug = match.group("doi_slug")

    record = load_registry().get(doc_id)
    doi = normalize_doi(str(record.get("doi"))) if record and record.get("doi") else None

    if not doi:
        recovered = _resolve_metadata_for_pdf(doc_id, doi_slug)
        if not recovered:
            raise RuntimeError(
                f"No existe registro en {ctx.REGISTRY_FILE} para document_id={doc_id} y no se pudo resolver DOI desde metadata"
            )

        doc_id = recovered["document_id"]
        doi = recovered["doi"]
        base_name = build_base_name(doc_id, doi)
        upsert_registry_record({"document_id": doc_id, "doi": doi}, base_name)
        return doc_id, doi, base_name

    base_name = build_base_name(doc_id, doi)
    return doc_id, doi, base_name
