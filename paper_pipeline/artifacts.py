from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config_loader as ctx


DOI_BASE_NAME_RE = re.compile(r"^doi-(?P<doi_slug>.+)$")
LEGACY_BASE_NAME_RE = re.compile(r"^(?P<docid>[^_]+)__doi-(?P<doi_slug>.+)$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_doi(doi: str) -> str:
    value = doi.strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    return value.strip().lower()


def slugify_doi(doi: str) -> str:
    normalized = normalize_doi(doi)
    slug = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown-doi"


def build_base_name(doi: str) -> str:
    return f"doi-{slugify_doi(doi)}"


def build_legacy_base_name(document_id: str, doi: str) -> str:
    return f"{document_id}__doi-{slugify_doi(doi)}"


def parse_base_name(value: str) -> dict[str, str] | None:
    doi_match = DOI_BASE_NAME_RE.match(value)
    if doi_match:
        return {"format": "doi", "doi_slug": doi_match.group("doi_slug")}

    legacy_match = LEGACY_BASE_NAME_RE.match(value)
    if legacy_match:
        return {
            "format": "legacy",
            "doi_slug": legacy_match.group("doi_slug"),
            "document_id": legacy_match.group("docid"),
        }

    return None


def trace_block(document_id: str, doi: str) -> dict[str, str]:
    return {
        "document_id": document_id,
        "doi": normalize_doi(doi),
        "created_at": utc_now_iso(),
    }


def registry_key_for_doi(doi: str) -> str:
    return normalize_doi(doi)


def load_registry() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not ctx.REGISTRY_FILE.exists():
        return records

    for line in ctx.REGISTRY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        data = json.loads(line)
        doi = str(data.get("doi") or "").strip()
        if not doi:
            continue

        records[registry_key_for_doi(doi)] = data

    return records


def save_registry(records: dict[str, dict[str, Any]]) -> None:
    ordered = sorted(
        records.values(),
        key=lambda item: (
            str(item.get("doi") or ""),
            str(item.get("document_id") or ""),
        ),
    )
    lines = [json.dumps(record, ensure_ascii=False) for record in ordered]
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


def _metadata_section(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    section = payload.get("metadata")
    if isinstance(section, dict):
        return section
    return payload


def _iter_metadata_entries(metadata_dir: Path | None = None) -> list[dict[str, str]]:
    resolved_dir = metadata_dir or ctx.METADATA_DIR
    entries: list[dict[str, str]] = []
    if not resolved_dir.exists():
        return entries

    for metadata_file in sorted(resolved_dir.glob("*.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        section = _metadata_section(payload)
        if not section:
            continue

        doi = section.get("doi")
        if not doi:
            continue

        document_id = section.get("document_id") or section.get("paperId") or ""
        normalized_doi = normalize_doi(str(doi))
        entries.append(
            {
                "document_id": str(document_id),
                "doi": normalized_doi,
                "doi_slug": slugify_doi(normalized_doi),
                "base_name": build_base_name(normalized_doi),
                "legacy_base_name": build_legacy_base_name(str(document_id), normalized_doi) if document_id else "",
                "path": str(metadata_file),
            }
        )

    return entries


def metadata_path_for_base_name(base_name: str, metadata_dir: Path | None = None) -> Path | None:
    resolved_dir = metadata_dir or ctx.METADATA_DIR
    direct_path = resolved_dir / f"{base_name}.metadata.json"
    if direct_path.exists():
        return direct_path

    parsed = parse_base_name(base_name)
    doi_slug = parsed["doi_slug"] if parsed else None
    document_id = parsed.get("document_id", "") if parsed else ""

    for entry in _iter_metadata_entries(resolved_dir):
        if entry["base_name"] == base_name:
            return Path(entry["path"])
        if doi_slug and entry["doi_slug"] == doi_slug:
            return Path(entry["path"])
        if document_id and entry["document_id"] == document_id:
            return Path(entry["path"])

    if document_id:
        legacy_path = resolved_dir / f"{document_id}.json"
        if legacy_path.exists():
            return legacy_path

    return None


def metadata_exists_for_base_name(base_name: str) -> bool:
    return metadata_path_for_base_name(base_name) is not None


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

    document_id = str(metadata.get("document_id") or "")
    doi = normalize_doi(str(metadata["doi"]))
    artifact_paths = artifact_paths_for_base_name(base_name)
    entry = records.get(registry_key_for_doi(doi), {})
    entry.update(
        {
            "document_id": document_id,
            "doi": doi,
            "base_name": base_name,
            "updated_at": utc_now_iso(),
            "paths": {name: str(path) for name, path in artifact_paths.items()},
            "stage_status": artifact_stage_status(artifact_paths),
        }
    )

    records[registry_key_for_doi(doi)] = entry
    save_registry(records)
    return entry


def refresh_registry_record(document_id: str, doi: str, base_name: str) -> dict[str, Any]:
    return upsert_registry_record({"document_id": document_id, "doi": doi}, base_name)


def record_claims_run(
    *,
    document_id: str,
    doi: str,
    base_name: str,
    claims_run: dict[str, Any],
) -> dict[str, Any]:
    upsert_registry_record({"document_id": document_id, "doi": doi}, base_name)
    records = load_registry()
    key = registry_key_for_doi(doi)
    entry = records.get(key, {})
    entry["claims_run"] = claims_run
    entry["updated_at"] = utc_now_iso()
    records[key] = entry
    save_registry(records)
    return entry


def _find_registry_record(document_id: str | None, doi_slug: str) -> dict[str, Any] | None:
    for record in load_registry().values():
        doi = str(record.get("doi") or "").strip()
        if doi and slugify_doi(doi) == doi_slug:
            return record

    if document_id:
        for record in load_registry().values():
            if str(record.get("document_id") or "").strip() == document_id:
                return record

    return None


def _resolve_metadata_for_pdf(document_id: str | None, doi_slug: str) -> dict[str, str] | None:
    entries = _iter_metadata_entries()

    for entry in entries:
        if entry["doi_slug"] == doi_slug:
            return entry

    if document_id:
        for entry in entries:
            if entry["document_id"] == document_id:
                return entry

    return None


def parse_document_from_pdf_name(pdf_path: Path) -> tuple[str, str, str]:
    parsed = parse_base_name(pdf_path.stem)
    if not parsed:
        raise RuntimeError(
            f"PDF no cumple convencion 'doi-<doi_slug>.pdf' ni '<document_id>__doi-<doi_slug>.pdf': {pdf_path.name}"
        )

    document_id = parsed.get("document_id")
    doi_slug = parsed["doi_slug"]

    record = _find_registry_record(document_id, doi_slug)
    doi = normalize_doi(str(record.get("doi"))) if record and record.get("doi") else None
    resolved_document_id = str(record.get("document_id") or document_id or "") if record else str(document_id or "")

    if not doi:
        recovered = _resolve_metadata_for_pdf(document_id, doi_slug)
        if not recovered:
            raise RuntimeError(
                f"No existe registro en {ctx.REGISTRY_FILE} ni metadata resoluble para doi_slug={doi_slug}"
            )

        resolved_document_id = recovered["document_id"]
        doi = recovered["doi"]

    base_name = build_base_name(doi)
    upsert_registry_record({"document_id": resolved_document_id, "doi": doi}, base_name)
    return resolved_document_id, doi, base_name
