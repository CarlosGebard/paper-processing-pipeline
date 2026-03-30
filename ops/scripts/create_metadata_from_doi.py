#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx
from src.artifacts import build_base_name, normalize_doi


SEMANTIC_URL = str(ctx.get_config().get("api", {}).get("semantic_scholar_url", "https://api.semanticscholar.org/graph/v1"))
SEMANTIC_API_KEY = ctx.get_env_or_config(
    "SEMANTIC_SCHOLAR_API_KEY",
    "api",
    "semantic_scholar_api_key",
    config=ctx.get_config(),
)
DOI_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "year",
        "citationCount",
        "externalIds",
        "openAccessPdf",
        "abstract",
        "authors",
    ]
)
REQUEST_INTERVAL_SECONDS = 1.0
_last_request_ts = 0.0


def build_metadata_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    external_ids = candidate.get("externalIds") or {}
    open_access_pdf = candidate.get("openAccessPdf") or {}
    authors = candidate.get("authors") or []

    return {
        "paperId": candidate.get("paperId"),
        "title": candidate.get("title"),
        "year": candidate.get("year"),
        "citationCount": candidate.get("citationCount"),
        "doi": external_ids.get("DOI"),
        "arxiv": external_ids.get("ArXiv"),
        "pdf_url": open_access_pdf.get("url"),
        "abstract": candidate.get("abstract"),
        "parent_papers": [],
        "authors": [author.get("name") for author in authors if isinstance(author, dict) and author.get("name")],
    }


def metadata_output_path(output_dir: Path, record: dict[str, Any], requested_doi: str) -> Path:
    doi = str(record.get("doi") or "").strip() or normalize_doi(requested_doi)
    paper_id = str(record.get("paperId") or "").strip()
    stem = build_base_name(doi) if doi else paper_id
    if not stem:
        raise ValueError("No se pudo construir nombre de archivo para metadata.")
    return output_dir / f"{stem}.metadata.json"


def create_session(api_key: str | None = None) -> requests.Session:
    session = requests.Session()
    if api_key:
        session.headers.update({"x-api-key": api_key})
    return session


def semantic_rate_limit() -> None:
    global _last_request_ts
    now = time.monotonic()
    elapsed = now - _last_request_ts
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_ts = time.monotonic()


def request_with_backoff(session: requests.Session, url: str, *, params: dict[str, Any]) -> requests.Response:
    retries = int(ctx.get_config().get("rate_limit", {}).get("retries", 5))
    base_delay = float(ctx.get_config().get("rate_limit", {}).get("base_delay", 1.0))
    max_delay = float(ctx.get_config().get("rate_limit", {}).get("max_delay", 30.0))

    for attempt in range(retries):
        semantic_rate_limit()
        response = session.get(url, params=params, timeout=60)
        if response.status_code == 200:
            return response
        if response.status_code in (429, 500, 502, 503, 504):
            delay = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 1)
            time.sleep(delay)
            continue
        response.raise_for_status()

    raise RuntimeError("Max retries exceeded while querying Semantic Scholar.")


def fetch_paper_by_doi(session: requests.Session, doi: str) -> dict[str, Any]:
    normalized_doi = normalize_doi(doi)
    url = f"{SEMANTIC_URL}/paper/DOI:{normalized_doi}"
    response = request_with_backoff(session, url, params={"fields": DOI_FIELDS})
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("paperId"):
        raise RuntimeError(f"Semantic Scholar no devolvio metadata valida para DOI {normalized_doi}.")
    return payload


def write_metadata_for_doi(
    doi: str,
    *,
    output_dir: Path,
    session: requests.Session,
    overwrite: bool = False,
) -> tuple[Path, str]:
    normalized_doi = normalize_doi(doi)
    paper = fetch_paper_by_doi(session, normalized_doi)
    metadata = build_metadata_payload(paper)
    output_path = metadata_output_path(output_dir, metadata, normalized_doi)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not overwrite:
        return output_path, "skipped_existing"

    output_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path, "written"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch one paper by DOI from Semantic Scholar and write canonical metadata JSON."
    )
    parser.add_argument("--doi", required=True, help="DOI del paper a guardar como metadata")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ctx.METADATA_DIR,
        help=f"Directorio de salida (default: {ctx.display_path(ctx.METADATA_DIR)})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobrescribe el archivo metadata si ya existe",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        ctx.ensure_dirs()
        session = create_session(SEMANTIC_API_KEY)
        output_path, status = write_metadata_for_doi(
            args.doi,
            output_dir=args.output_dir.expanduser().resolve(),
            session=session,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if status == "skipped_existing":
        print(f"[SKIP EXISTING] {output_path}")
        return 0

    print(f"[OK] Metadata guardada en {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
