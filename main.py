#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from config_loader import DATA_DIR, ROOT_DIR, get_config, get_pipeline_paths


CONFIG = get_config()
PATHS = get_pipeline_paths(CONFIG)

METADATA_DIR = PATHS["metadata_dir"]
DOCLING_INPUT_DIR = PATHS["docling_input_dir"]
DOCLING_JSON_DIR = PATHS["docling_json_dir"]
DOCLING_MD_DIR = PATHS["docling_markdown_dir"]
HEURISTICS_FULL_DIR = PATHS["heuristics_full_dir"]
HEURISTICS_FINAL_DIR = PATHS["heuristics_final_dir"]
CLAIMS_INPUT_DIR = PATHS["claims_input_dir"]
CLAIMS_OUTPUT_DIR = PATHS["claims_output_dir"]
REGISTRY_DIR = PATHS["registry_dir"]
RAW_PDF_DIR = PATHS["raw_pdf_dir"]

LLM_CLAIMS_CFG = CONFIG.get("llm_to_claim") or {}
LLM_CLAIMS_MODEL = str(LLM_CLAIMS_CFG.get("model", "gpt-5-mini"))
LLM_CLAIMS_MAX = int(LLM_CLAIMS_CFG.get("max_claims", 10))
LLM_CLAIMS_TEMPERATURE = float(LLM_CLAIMS_CFG.get("temperature", 0.0))

REGISTRY_FILE = REGISTRY_DIR / "documents.jsonl"
BIB_OUTPUT_FILE = METADATA_DIR / "papers.bib"
OPENALEX_BASE = "https://api.openalex.org"

SCRIPTS_DIR = ROOT_DIR / "scripts"
SCRIPT_DOCLING_INGEST = SCRIPTS_DIR / "docling_ingest_pdf.py"
SCRIPT_JSON_TO_BIB = SCRIPTS_DIR / "json_to_bib.py"
SCRIPT_NORMALIZE_RAW = SCRIPTS_DIR / "normalize_raw_pdfs.py"
SCRIPT_EXPLORE_CITATIONS = SCRIPTS_DIR / "explore_citations_semantic.py"
SCRIPT_LLM_TO_CLAIM = SCRIPTS_DIR / "llm_to_claim.py"
HEURISTICS_SRC_DIR = SCRIPTS_DIR / "heuristics_model" / "src"


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


def ensure_dirs() -> None:
    required_dirs = (
        DATA_DIR,
        METADATA_DIR,
        DOCLING_INPUT_DIR,
        DOCLING_JSON_DIR,
        DOCLING_MD_DIR,
        HEURISTICS_FULL_DIR,
        HEURISTICS_FINAL_DIR,
        CLAIMS_OUTPUT_DIR,
        REGISTRY_DIR,
        RAW_PDF_DIR,
    )
    for directory in required_dirs:
        directory.mkdir(parents=True, exist_ok=True)


def _load_module(script_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def resolve_docling_convert_pdf() -> Callable[[Path, Path, bool], tuple[Path, Path]]:
    module = _load_module(SCRIPT_DOCLING_INGEST, "docling_ingest_pdf")
    return module.convert_pdf


@lru_cache(maxsize=1)
def resolve_generate_bib() -> Callable[[Path, Path], tuple[int, int]]:
    module = _load_module(SCRIPT_JSON_TO_BIB, "json_to_bib_module")
    return module.generate_bib


@lru_cache(maxsize=1)
def resolve_raw_pdf_sync() -> Callable[[Path, Path, Path, Path | None], tuple[int, int]]:
    module = _load_module(SCRIPT_NORMALIZE_RAW, "docling_normalize_raw_pdfs")
    return module.sync_raw_pdfs_into_input


@lru_cache(maxsize=1)
def resolve_claims_flow() -> Callable[[Path, Path, str, int, float, str], tuple[int, int]]:
    module = _load_module(SCRIPT_LLM_TO_CLAIM, "llm_to_claim_module")
    return module.run_claim_extraction_flow


@lru_cache(maxsize=1)
def load_heuristics_functions() -> tuple[Callable[..., Any], Callable[..., str]]:
    if str(HEURISTICS_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(HEURISTICS_SRC_DIR))

    from heuristics_model.pipeline import process_markdown  # type: ignore
    from heuristics_model.rendering import render_markdown  # type: ignore

    return process_markdown, render_markdown


def parse_document_id_from_openalex(work_id: str | None) -> str | None:
    if not work_id:
        return None
    candidate = work_id.rstrip("/").split("/")[-1]
    if re.match(r"^[A-Za-z0-9]+$", candidate):
        return candidate
    return None


def fallback_document_id(doi: str) -> str:
    digest = hashlib.sha1(normalize_doi(doi).encode("utf-8")).hexdigest()[:12]
    return f"DOC{digest}"


def fetch_openalex_metadata(doi: str) -> dict[str, Any]:
    normalized_doi = normalize_doi(doi)
    url = f"{OPENALEX_BASE}/works/doi:{quote(normalized_doi, safe='')}"
    req = Request(url, headers={"User-Agent": "paper-processing-pipeline/1.0"})

    try:
        with urlopen(req, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"OpenAlex devolvio HTTP {exc.code} para DOI {normalized_doi}") from exc
    except URLError as exc:
        raise RuntimeError(f"No fue posible conectar con OpenAlex: {exc.reason}") from exc

    doc_id = parse_document_id_from_openalex(payload.get("id")) or fallback_document_id(normalized_doi)

    locations = payload.get("locations") or []
    pdf_url = (payload.get("primary_location") or {}).get("pdf_url")
    if not pdf_url:
        for location in locations:
            candidate = location.get("pdf_url")
            if candidate:
                pdf_url = candidate
                break

    authors: list[str] = []
    for authorship in payload.get("authorships", []):
        display_name = (authorship.get("author") or {}).get("display_name")
        if display_name:
            authors.append(display_name)

    return {
        "document_id": doc_id,
        "doi": normalized_doi,
        "title": payload.get("title"),
        "year": payload.get("publication_year"),
        "citation_count": payload.get("cited_by_count"),
        "authors": authors,
        "pdf_url": pdf_url,
        "openalex_id": payload.get("id"),
    }


def load_registry() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not REGISTRY_FILE.exists():
        return records

    for line in REGISTRY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        records[data["document_id"]] = data

    return records


def save_registry(records: dict[str, dict[str, Any]]) -> None:
    lines = [json.dumps(records[document_id], ensure_ascii=False) for document_id in sorted(records.keys())]
    REGISTRY_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def artifact_paths_for_base_name(base_name: str) -> dict[str, Path]:
    return {
        "metadata": METADATA_DIR / f"{base_name}.metadata.json",
        "pdf": DOCLING_INPUT_DIR / f"{base_name}.pdf",
        "docling_json": DOCLING_JSON_DIR / f"{base_name}.docling.json",
        "docling_markdown": DOCLING_MD_DIR / f"{base_name}.docling.md",
        "heuristics_full": HEURISTICS_FULL_DIR / f"{base_name}.heuristics.full.md",
        "heuristics_final": HEURISTICS_FINAL_DIR / f"{base_name}.heuristics.final.md",
        "claims": CLAIMS_OUTPUT_DIR / f"{base_name}.claims.json",
    }


def metadata_exists_for_base_name(base_name: str) -> bool:
    default_path = METADATA_DIR / f"{base_name}.metadata.json"
    if default_path.exists():
        return True

    document_id = base_name.split("__doi-", 1)[0]
    legacy_path = METADATA_DIR / f"{document_id}.json"
    return legacy_path.exists()


def artifact_stage_status(paths: dict[str, Path]) -> dict[str, bool]:
    return {
        "metadata": metadata_exists_for_base_name(paths["metadata"].stem.replace(".metadata", "")),
        "pdf": paths["pdf"].exists(),
        "docling": paths["docling_json"].exists() and paths["docling_markdown"].exists(),
        "heuristics": paths["heuristics_full"].exists() and paths["heuristics_final"].exists(),
        "claims": paths["claims"].exists(),
        "completed": (
            paths["docling_json"].exists()
            and paths["docling_markdown"].exists()
            and paths["heuristics_full"].exists()
            and paths["heuristics_final"].exists()
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


def save_metadata(metadata: dict[str, Any]) -> Path:
    base_name = build_base_name(metadata["document_id"], metadata["doi"])
    output_path = METADATA_DIR / f"{base_name}.metadata.json"
    payload = {
        "trace": trace_block(metadata["document_id"], metadata["doi"]),
        "metadata": metadata,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_registry_record(metadata, base_name)
    return output_path


def maybe_copy_pdf(metadata: dict[str, Any], source_pdf: str | None) -> Path | None:
    if not source_pdf:
        return None

    source_path = Path(source_pdf).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"No existe el PDF indicado: {source_path}")

    target_path = DOCLING_INPUT_DIR / f"{build_base_name(metadata['document_id'], metadata['doi'])}.pdf"
    shutil.copy2(source_path, target_path)
    return target_path


def _metadata_section(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    section = payload.get("metadata")
    if isinstance(section, dict):
        return section
    return payload


def _iter_metadata_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if not METADATA_DIR.exists():
        return entries

    for metadata_file in sorted(METADATA_DIR.glob("*.json")):
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
                f"No existe registro en {REGISTRY_FILE} para document_id={doc_id} y no se pudo resolver DOI desde metadata"
            )

        doc_id = recovered["document_id"]
        doi = recovered["doi"]
        base_name = build_base_name(doc_id, doi)
        upsert_registry_record({"document_id": doc_id, "doi": doi}, base_name)
        return doc_id, doi, base_name

    base_name = build_base_name(doc_id, doi)
    return doc_id, doi, base_name


def strip_leading_trace_comments(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    while lines and lines[0].strip().startswith("<!--"):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines)


def _display_heading(text: str) -> str:
    return text.replace("_", " ").title()


def _render_section_body(section: Any) -> str:
    lines: list[str] = []

    for node in section.content:
        lines.append(node.text)
        lines.append("")

    for subsection in section.subsections:
        lines.append(f"## {_display_heading(subsection.title)}")
        lines.append("")
        for node in subsection.content:
            lines.append(node.text)
            lines.append("")

    return "\n".join(lines).strip()


def _render_subsection_body(subsection: Any) -> str:
    lines: list[str] = []
    for node in subsection.content:
        lines.append(node.text)
        lines.append("")
    return "\n".join(lines).strip()


def _first_matching_section_body(section_map: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        section = section_map.get(alias)
        if section is None:
            continue
        body = _render_section_body(section)
        if body:
            return body
    return ""


def _first_matching_subsection_body(structure: Any, aliases: tuple[str, ...]) -> str:
    alias_set = set(aliases)
    for section in structure.sections:
        for subsection in section.subsections:
            if subsection.title not in alias_set:
                continue
            body = _render_subsection_body(subsection)
            if body:
                return body
    return ""


def build_final_markdown_output(structure: Any, document_id: str, doi: str) -> str:
    section_map = {section.title: section for section in structure.sections}
    methods_aliases = (
        "methods",
        "method",
        "materials and methods",
        "materials and method",
        "materials & methods",
        "materials & method",
        "methods and materials",
        "patients and methods",
        "patients and method",
        "methodology",
    )
    results_aliases = ("results", "result", "results_discussion")

    methods_body = _first_matching_section_body(section_map, methods_aliases)
    if not methods_body:
        methods_body = _first_matching_subsection_body(structure, methods_aliases)

    results_body = _first_matching_section_body(section_map, results_aliases)
    if not results_body:
        results_body = _first_matching_subsection_body(structure, results_aliases)

    include_abstract = not methods_body or not results_body
    abstract_body = _first_matching_section_body(section_map, ("abstract",))

    lines: list[str] = [
        "# Trace",
        "",
        f"- document_id: {document_id}",
        f"- doi: {normalize_doi(doi)}",
        f"- creation_date: {utc_now_iso()}",
        "",
        "# Methods",
        "",
        methods_body or "_Section not found in source document._",
        "",
        "# Results",
        "",
        results_body or "_Section not found in source document._",
    ]

    if include_abstract:
        lines.extend(
            [
                "",
                "# Abstract",
                "",
                abstract_body or "_Section not found in source document._",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def list_pdf_candidates() -> list[Path]:
    if not DOCLING_INPUT_DIR.exists():
        return []
    return sorted({p.resolve() for p in DOCLING_INPUT_DIR.glob("*.pdf")})


def run_docling_for_pdf(pdf_path: Path, enable_ocr: bool) -> tuple[Path, Path, str, str, str]:
    document_id, doi, base_name = parse_document_from_pdf_name(pdf_path)
    convert_pdf = resolve_docling_convert_pdf()

    with TemporaryDirectory(prefix="docling_tmp_", dir=str(DATA_DIR)) as tmp_dir:
        tmp_output_dir = Path(tmp_dir)
        tmp_json, tmp_md = convert_pdf(pdf_path, tmp_output_dir, enable_ocr)

        json_target = DOCLING_JSON_DIR / f"{base_name}.docling.json"
        md_target = DOCLING_MD_DIR / f"{base_name}.docling.md"

        raw_json = json.loads(tmp_json.read_text(encoding="utf-8"))
        wrapped_json = {
            "trace": trace_block(document_id, doi),
            "source_pdf": str(pdf_path),
            "docling": raw_json,
        }
        json_target.write_text(json.dumps(wrapped_json, ensure_ascii=False, indent=2), encoding="utf-8")

        raw_md = tmp_md.read_text(encoding="utf-8")
        prefixed_md = (
            f"<!-- document_id: {document_id} -->\n"
            f"<!-- doi: {normalize_doi(doi)} -->\n\n"
            f"{raw_md}"
        )
        md_target.write_text(prefixed_md, encoding="utf-8")

    return json_target, md_target, document_id, doi, base_name


def run_heuristics_for_markdown(
    markdown_path: Path,
    document_id: str,
    doi: str,
    base_name: str,
) -> tuple[Path, Path]:
    process_markdown, render_markdown = load_heuristics_functions()

    cleaned_markdown = strip_leading_trace_comments(markdown_path.read_text(encoding="utf-8"))
    structure = process_markdown(cleaned_markdown)

    full_doc = (
        f"<!-- document_id: {document_id} -->\n"
        f"<!-- doi: {normalize_doi(doi)} -->\n\n"
        f"{render_markdown(structure)}"
    )

    full_path = HEURISTICS_FULL_DIR / f"{base_name}.heuristics.full.md"
    final_path = HEURISTICS_FINAL_DIR / f"{base_name}.heuristics.final.md"

    full_path.write_text(full_doc, encoding="utf-8")

    final_markdown = build_final_markdown_output(
        structure=structure,
        document_id=document_id,
        doi=doi,
    )
    final_path.write_text(final_markdown, encoding="utf-8")

    return full_path, final_path


def sync_raw_pdfs() -> tuple[int, int]:
    sync_raw = resolve_raw_pdf_sync()
    return sync_raw(RAW_PDF_DIR, DOCLING_INPUT_DIR, METADATA_DIR, BIB_OUTPUT_FILE)


def fetch_metadata_flow(doi: str, source_pdf: str | None) -> None:
    ensure_dirs()
    metadata = fetch_openalex_metadata(doi)
    metadata_path = save_metadata(metadata)
    copied_pdf = maybe_copy_pdf(metadata, source_pdf)

    print("Metadata guardada")
    print(f"- DOI: {metadata['doi']}")
    print(f"- Document ID: {metadata['document_id']}")
    print(f"- Archivo metadata: {metadata_path}")

    if copied_pdf:
        print(f"- PDF copiado a: {copied_pdf}")
        return

    expected_pdf = DOCLING_INPUT_DIR / f"{build_base_name(metadata['document_id'], metadata['doi'])}.pdf"
    print(f"- Para seguir con pipeline, deja el PDF en: {expected_pdf}")


def run_metadata_exploration_flow() -> None:
    if not SCRIPT_EXPLORE_CITATIONS.exists():
        raise FileNotFoundError(f"No existe el script requerido: {SCRIPT_EXPLORE_CITATIONS}")

    result = subprocess.run([sys.executable, str(SCRIPT_EXPLORE_CITATIONS)], cwd=str(ROOT_DIR))
    if result.returncode != 0:
        raise RuntimeError(
            f"Fallo la exploracion de metadata (codigo de salida {result.returncode})"
        )


def run_pipeline_flow(enable_ocr: bool) -> None:
    ensure_dirs()
    copied_raw, skipped_raw = sync_raw_pdfs()

    pdfs = list_pdf_candidates()
    if not pdfs:
        print(f"No hay PDFs en {DOCLING_INPUT_DIR}.")
        return

    processed_docling = 0
    processed_heuristics = 0
    skipped_complete = 0
    skipped_existing_heuristics = 0
    failed = 0

    for pdf_path in pdfs:
        try:
            document_id, doi, base_name = parse_document_from_pdf_name(pdf_path)
            record = refresh_registry_record(document_id, doi, base_name)
            stage_status = record.get("stage_status", {})

            if stage_status.get("completed"):
                print(f"[SKIP COMPLETE] {pdf_path.name}")
                skipped_complete += 1
                continue

            artifact_paths = artifact_paths_for_base_name(base_name)

            if stage_status.get("heuristics"):
                print(f"[SKIP HEURISTICS] {pdf_path.name}: ya existe salida heuristics")
                skipped_existing_heuristics += 1
                continue

            if stage_status.get("docling"):
                docling_json = artifact_paths["docling_json"]
                docling_md = artifact_paths["docling_markdown"]
            else:
                docling_json, docling_md, _, _, _ = run_docling_for_pdf(pdf_path, enable_ocr)
                processed_docling += 1

            heuristics_full, heuristics_final = run_heuristics_for_markdown(
                docling_md,
                document_id=document_id,
                doi=doi,
                base_name=base_name,
            )
            refresh_registry_record(document_id, doi, base_name)
            print(f"[OK] {pdf_path.name}")
            print(f"  - Docling JSON: {docling_json}")
            print(f"  - Docling MD:   {docling_md}")
            print(f"  - Heuristics full:  {heuristics_full}")
            print(f"  - Heuristics final: {heuristics_final}")
            processed_heuristics += 1
        except Exception as exc:
            print(f"[SKIP] {pdf_path.name}: {exc}")
            failed += 1

    print("\nResumen pipeline")
    print(f"- Raw copiados:            {copied_raw}")
    print(f"- Raw omitidos:            {skipped_raw}")
    print(f"- Docling procesados:      {processed_docling}")
    print(f"- Heuristics procesados:   {processed_heuristics}")
    print(f"- Saltados completos:      {skipped_complete}")
    print(f"- Saltados por heuristics: {skipped_existing_heuristics}")
    print(f"- Fallidos:                {failed}")


def run_end_to_end_flow(
    enable_ocr: bool,
    model: str | None = None,
    max_claims: int | None = None,
    temperature: float | None = None,
) -> None:
    ensure_dirs()
    copied_raw, skipped_raw = sync_raw_pdfs()

    pdfs = list_pdf_candidates()
    if not pdfs:
        print(f"No hay PDFs en {DOCLING_INPUT_DIR}.")
        return

    chosen_model = model or LLM_CLAIMS_MODEL
    chosen_max = max_claims if max_claims is not None else LLM_CLAIMS_MAX
    chosen_temp = temperature if temperature is not None else LLM_CLAIMS_TEMPERATURE

    docling_processed = 0
    heuristics_processed = 0
    claims_processed = 0
    skipped_complete = 0
    failed = 0
    pending_claim_inputs: list[tuple[str, str, str, Path]] = []

    for pdf_path in pdfs:
        try:
            document_id, doi, base_name = parse_document_from_pdf_name(pdf_path)
            record = refresh_registry_record(document_id, doi, base_name)
            stage_status = record.get("stage_status", {})

            if stage_status.get("completed"):
                print(f"[SKIP COMPLETE] {pdf_path.name}")
                skipped_complete += 1
                continue

            artifact_paths = artifact_paths_for_base_name(base_name)

            if stage_status.get("docling"):
                docling_md = artifact_paths["docling_markdown"]
            else:
                _, docling_md, _, _, _ = run_docling_for_pdf(pdf_path, enable_ocr)
                docling_processed += 1

            if not stage_status.get("heuristics"):
                run_heuristics_for_markdown(
                    docling_md,
                    document_id=document_id,
                    doi=doi,
                    base_name=base_name,
                )
                heuristics_processed += 1

            refreshed = refresh_registry_record(document_id, doi, base_name)
            final_md = Path(refreshed["paths"]["heuristics_final"])
            final_stage_status = refreshed.get("stage_status", {})

            if final_stage_status.get("claims"):
                print(f"[SKIP CLAIMS] {pdf_path.name}: ya existe salida claims")
                skipped_complete += 1
                continue

            pending_claim_inputs.append((document_id, doi, base_name, final_md))
        except Exception as exc:
            print(f"[SKIP] {pdf_path.name}: {exc}")
            failed += 1

    for document_id, doi, base_name, final_md in pending_claim_inputs:
        try:
            claims_flow = resolve_claims_flow()
            processed, skipped = claims_flow(
                final_md,
                CLAIMS_OUTPUT_DIR,
                chosen_model,
                chosen_max,
                chosen_temp,
                "*.heuristics.final.md",
            )
            claims_processed += processed
            if skipped and not processed:
                print(f"[SKIP CLAIMS] {final_md.name}")
            refresh_registry_record(document_id, doi, base_name)
        except Exception as exc:
            print(f"[SKIP CLAIMS] {final_md.name}: {exc}")
            failed += 1

    print("\nResumen process-all")
    print(f"- Raw copiados:          {copied_raw}")
    print(f"- Raw omitidos:          {skipped_raw}")
    print(f"- Docling procesados:    {docling_processed}")
    print(f"- Heuristics procesados: {heuristics_processed}")
    print(f"- Claims procesados:     {claims_processed}")
    print(f"- Saltados completos:    {skipped_complete}")
    print(f"- Fallidos:              {failed}")


def generate_bib_flow(output_file: Path | None = None) -> None:
    ensure_dirs()
    generator = resolve_generate_bib()
    target = output_file or BIB_OUTPUT_FILE
    entries, skipped = generator(METADATA_DIR, target)

    print("BibTeX generado")
    print(f"- Entradas: {entries}")
    print(f"- Omitidos: {skipped}")
    print(f"- Archivo:  {target}")


def normalize_pdfs_flow() -> None:
    ensure_dirs()
    copied_raw, skipped_raw = sync_raw_pdfs()

    print("Sincronizacion raw_pdf -> input_pdfs")
    print(f"- Copiados: {copied_raw}")
    print(f"- Omitidos: {skipped_raw}")


def run_llm_to_claim_flow(
    input_path: Path | None = None,
    output_path: Path | None = None,
    model: str | None = None,
    max_claims: int | None = None,
    temperature: float | None = None,
    pattern: str = "*.heuristics.final.md",
) -> None:
    ensure_dirs()
    claims_flow = resolve_claims_flow()

    source = (input_path or CLAIMS_INPUT_DIR).expanduser().resolve()
    target = (output_path or CLAIMS_OUTPUT_DIR).expanduser().resolve()
    chosen_model = model or LLM_CLAIMS_MODEL
    chosen_max = max_claims if max_claims is not None else LLM_CLAIMS_MAX
    chosen_temp = temperature if temperature is not None else LLM_CLAIMS_TEMPERATURE

    processed, skipped = claims_flow(
        source,
        target,
        chosen_model,
        chosen_max,
        chosen_temp,
        pattern,
    )

    print("Extraccion de claims completada")
    print(f"- Input:      {source}")
    print(f"- Output:     {target}")
    print(f"- Modelo:     {chosen_model}")
    print(f"- Max claims: {chosen_max}")
    print(f"- Procesados: {processed}")
    print(f"- Omitidos:   {skipped}")


def _run_menu_bib() -> None:
    output = input("Ruta .bib de salida (Enter para default): ").strip()
    target = Path(output).expanduser().resolve() if output else None
    try:
        generate_bib_flow(target)
    except Exception as exc:
        print(f"Error generando .bib: {exc}")


def _run_menu_claims() -> None:
    try:
        run_llm_to_claim_flow()
    except Exception as exc:
        print(f"Error en llm_to_claim: {exc}")


def interactive_menu() -> None:
    ensure_dirs()

    while True:
        print("\n=== Paper Processing CLI ===")
        print("1) Extraer metadata (script scripts/explore_citations_semantic.py)")
        print("2) Ejecutar pipeline completo (Docling + Heuristics)")
        print(f"3) Generar .bib desde {METADATA_DIR}")
        print("4) Normalizar PDFs (raw_pdf -> input_pdfs)")
        print(f"5) Extraer claims LLM ({CLAIMS_INPUT_DIR} -> {CLAIMS_OUTPUT_DIR})")
        print("6) Ejecutar flujo completo hasta claims")
        print("7) Salir")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            try:
                run_metadata_exploration_flow()
            except Exception as exc:
                print(f"Error en metadata: {exc}")
            continue

        if choice == "2":
            enable_ocr = input("Activar OCR? (y/N): ").strip().lower() == "y"
            run_pipeline_flow(enable_ocr=enable_ocr)
            continue

        if choice == "3":
            _run_menu_bib()
            continue

        if choice == "4":
            normalize_pdfs_flow()
            continue

        if choice == "5":
            _run_menu_claims()
            continue

        if choice == "6":
            enable_ocr = input("Activar OCR? (y/N): ").strip().lower() == "y"
            try:
                run_end_to_end_flow(enable_ocr=enable_ocr)
            except Exception as exc:
                print(f"Error en process-all: {exc}")
            continue

        if choice in {"7", "q", "Q", "exit", "EXIT", "salir", "SALIR"}:
            print("Saliendo.")
            return

        print("Opcion invalida.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI unificada para metadata DOI -> Docling -> Heuristics"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("menu", help="Abre menu interactivo")
    subparsers.add_parser("metadata", help="Ejecuta scripts/explore_citations_semantic.py")

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help=f"Ejecuta Docling + Heuristics para PDFs trazables en {DOCLING_INPUT_DIR}",
    )
    pipeline_parser.add_argument("--enable-ocr", action="store_true", help="Activa OCR en Docling")

    process_all_parser = subparsers.add_parser(
        "process-all",
        help=f"Ejecuta flujo completo raw_pdf -> claims saltando documentos ya completos",
    )
    process_all_parser.add_argument("--enable-ocr", action="store_true", help="Activa OCR en Docling")
    process_all_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Modelo (default config llm_to_claim.model: {LLM_CLAIMS_MODEL})",
    )
    process_all_parser.add_argument(
        "--max-claims",
        type=int,
        default=None,
        help=f"Max claims (default config llm_to_claim.max_claims: {LLM_CLAIMS_MAX})",
    )
    process_all_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Temperature (default config llm_to_claim.temperature: {LLM_CLAIMS_TEMPERATURE})",
    )

    bib_parser = subparsers.add_parser(
        "bib",
        help=f"Genera un archivo .bib a partir de metadata JSON en {METADATA_DIR}",
    )
    bib_parser.add_argument("--output", type=Path, default=None, help="Ruta opcional del archivo .bib de salida")

    subparsers.add_parser(
        "normalize-pdfs",
        help=f"Normaliza PDFs de {RAW_PDF_DIR} a {DOCLING_INPUT_DIR}",
    )

    claims_parser = subparsers.add_parser(
        "claims",
        help=f"Extrae claims desde {CLAIMS_INPUT_DIR} hacia {CLAIMS_OUTPUT_DIR}",
    )
    claims_parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Archivo/directorio de entrada (default config llm_to_claim.input_dir)",
    )
    claims_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Archivo/directorio de salida (default config llm_to_claim.output_dir)",
    )
    claims_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Modelo (default config llm_to_claim.model: {LLM_CLAIMS_MODEL})",
    )
    claims_parser.add_argument(
        "--max-claims",
        type=int,
        default=None,
        help=f"Max claims (default config llm_to_claim.max_claims: {LLM_CLAIMS_MAX})",
    )
    claims_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Temperature (default config llm_to_claim.temperature: {LLM_CLAIMS_TEMPERATURE})",
    )
    claims_parser.add_argument(
        "--pattern",
        type=str,
        default="*.heuristics.final.md",
        help="Glob pattern cuando --input es directorio",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in (None, "menu"):
        interactive_menu()
        return

    if args.command == "metadata":
        run_metadata_exploration_flow()
        return

    if args.command == "pipeline":
        run_pipeline_flow(enable_ocr=args.enable_ocr)
        return

    if args.command == "process-all":
        run_end_to_end_flow(
            enable_ocr=args.enable_ocr,
            model=args.model,
            max_claims=args.max_claims,
            temperature=args.temperature,
        )
        return

    if args.command == "bib":
        target = args.output.expanduser().resolve() if args.output else None
        generate_bib_flow(target)
        return

    if args.command == "normalize-pdfs":
        normalize_pdfs_flow()
        return

    if args.command == "claims":
        run_llm_to_claim_flow(
            input_path=args.input,
            output_path=args.output,
            model=args.model,
            max_claims=args.max_claims,
            temperature=args.temperature,
            pattern=args.pattern,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
