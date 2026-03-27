#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config_loader as ctx
from paper_pipeline.artifacts import build_base_name, normalize_doi


SEMANTIC_URL = str(ctx.get_config().get("api", {}).get("semantic_scholar_url", "https://api.semanticscholar.org/graph/v1"))
SEMANTIC_API_KEY = ctx.get_env_or_config(
    "SEMANTIC_SCHOLAR_API_KEY",
    "api",
    "semantic_scholar_api_key",
    config=ctx.get_config(),
)

SEARCH_FIELDS = ",".join(
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


@dataclass
class SearchDecision:
    matched: bool
    reason: str
    candidate: dict[str, Any] | None = None
    ratio: float = 0.0


def normalize_title_key(value: str) -> str:
    lowered = value.lower().strip()
    normalized = unicodedata.normalize("NFKD", lowered)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_only).strip()


def title_similarity(left: str, right: str) -> float:
    left_key = normalize_title_key(left)
    right_key = normalize_title_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return difflib.SequenceMatcher(None, left_key, right_key).ratio()


def metadata_file_path(directory: Path, record: dict[str, Any]) -> Path:
    doi = str(record.get("doi") or "").strip()
    paper_id = str(record.get("paperId") or "").strip()
    stem = build_base_name(doi) if doi else paper_id
    return directory / f"{stem}.metadata.json"


def canonical_record_key(record: dict[str, Any]) -> str | None:
    doi = str(record.get("doi") or "").strip()
    if doi:
        return f"doi:{normalize_doi(doi)}"
    paper_id = str(record.get("paperId") or "").strip()
    if paper_id:
        return f"paper:{paper_id}"
    return None


def collect_existing_metadata_keys(directory: Path) -> set[str]:
    keys: set[str] = set()
    if not directory.exists():
        return keys

    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        key = canonical_record_key(payload if isinstance(payload, dict) else {})
        if key:
            keys.add(key)
    return keys


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


def search_semantic_scholar_by_title(
    session: requests.Session,
    *,
    title: str,
    limit: int,
) -> list[dict[str, Any]]:
    url = f"{SEMANTIC_URL}/paper/search"
    params = {
        "query": title,
        "limit": limit,
        "fields": SEARCH_FIELDS,
    }
    response = request_with_backoff(session, url, params=params)
    return list(response.json().get("data") or [])


def choose_best_title_match(
    source_title: str,
    source_year: int | None,
    candidates: list[dict[str, Any]],
    *,
    min_similarity: float = 0.93,
) -> SearchDecision:
    ranked: list[tuple[float, int, int, dict[str, Any]]] = []
    for candidate in candidates:
        candidate_title = str(candidate.get("title") or "")
        ratio = title_similarity(source_title, candidate_title)
        if ratio <= 0:
            continue

        candidate_year = candidate.get("year")
        if source_year and candidate_year:
            year_penalty = abs(int(source_year) - int(candidate_year))
        else:
            year_penalty = 0

        doi_bonus = 1 if ((candidate.get("externalIds") or {}).get("DOI")) else 0
        ranked.append((ratio, doi_bonus, -year_penalty, candidate))

    if not ranked:
        return SearchDecision(matched=False, reason="no_candidates")

    ranked.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
    best_ratio, _, _, best_candidate = ranked[0]
    if best_ratio < min_similarity:
        return SearchDecision(matched=False, reason=f"low_similarity:{best_ratio:.3f}", ratio=best_ratio)

    if source_year and best_candidate.get("year"):
        delta = abs(int(source_year) - int(best_candidate["year"]))
        if delta > 2:
            return SearchDecision(
                matched=False,
                reason=f"year_mismatch:{delta}",
                candidate=best_candidate,
                ratio=best_ratio,
            )

    return SearchDecision(
        matched=True,
        reason="matched",
        candidate=best_candidate,
        ratio=best_ratio,
    )


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_source_directory(
    source_dir: Path,
    *,
    canonical_metadata_dir: Path,
    session: requests.Session,
    search_limit: int,
    min_similarity: float,
    dry_run: bool,
) -> dict[str, int]:
    stats = {
        "processed": 0,
        "matched": 0,
        "rewritten": 0,
        "promoted": 0,
        "duplicates": 0,
        "unmatched": 0,
        "invalid": 0,
    }
    existing_keys = collect_existing_metadata_keys(canonical_metadata_dir)
    local_keys: set[str] = set()

    for path in sorted(source_dir.glob("*.json")):
        stats["processed"] += 1
        raw = load_json(path)
        if not raw:
            stats["invalid"] += 1
            print(f"[INVALID] {path}")
            continue

        title = str(raw.get("title") or "").strip()
        source_year = raw.get("year")
        if not title:
            stats["unmatched"] += 1
            print(f"[NO TITLE] {path}")
            continue

        candidates = search_semantic_scholar_by_title(session, title=title, limit=search_limit)
        decision = choose_best_title_match(title, int(source_year) if isinstance(source_year, int) else None, candidates, min_similarity=min_similarity)
        if not decision.matched or not decision.candidate:
            stats["unmatched"] += 1
            print(f"[UNMATCHED] {path.name}: {decision.reason}")
            continue

        payload = build_metadata_payload(decision.candidate)
        target_path = metadata_file_path(source_dir, payload)
        key = canonical_record_key(payload)

        stats["matched"] += 1
        if key and key in local_keys:
            stats["duplicates"] += 1
            if path != target_path and not dry_run and path.exists():
                path.unlink()
            print(f"[LOCAL DUPLICATE] {path.name} -> {target_path.name}")
            continue

        if not dry_run:
            write_json(target_path, payload)
            if path != target_path and path.exists():
                path.unlink()
        stats["rewritten"] += 1
        if key:
            local_keys.add(key)

        if key and key not in existing_keys:
            canonical_target = metadata_file_path(canonical_metadata_dir, payload)
            if not dry_run:
                write_json(canonical_target, payload)
            existing_keys.add(key)
            stats["promoted"] += 1
            print(f"[PROMOTED] {target_path.name} -> {canonical_target.name}")
        else:
            stats["duplicates"] += 1

    return stats


def build_session(api_key: str | None) -> requests.Session:
    session = requests.Session()
    if api_key:
        session.headers.update({"x-api-key": api_key})
    return session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich dirty metadata folders by title using Semantic Scholar and promote unique records to canonical metadata."
    )
    parser.add_argument(
        "--source-dir",
        dest="source_dirs",
        action="append",
        type=Path,
        help="Source metadata directory. Can be passed multiple times.",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=ctx.METADATA_DIR,
        help="Canonical metadata directory where unique records are promoted.",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=10,
        help="Number of Semantic Scholar candidates requested per title.",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=0.93,
        help="Minimum normalized title similarity required to accept a match.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned matches/promotions without writing files.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Semantic Scholar API key override. Falls back to SEMANTIC_SCHOLAR_API_KEY or config.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key or SEMANTIC_API_KEY
    if not api_key:
        raise SystemExit("SEMANTIC_SCHOLAR_API_KEY is not set.")

    default_sources = [
        ROOT_DIR / "data" / "sources" / "discarded_papers",
        ROOT_DIR / "data" / "Extra papers" / "metadata",
    ]
    source_dirs = [path.expanduser().resolve() for path in (args.source_dirs or default_sources)]
    metadata_dir = args.metadata_dir.expanduser().resolve()
    metadata_dir.mkdir(parents=True, exist_ok=True)

    session = build_session(api_key)
    grand_total = {
        "processed": 0,
        "matched": 0,
        "rewritten": 0,
        "promoted": 0,
        "duplicates": 0,
        "unmatched": 0,
        "invalid": 0,
    }

    for source_dir in source_dirs:
        print(f"Processing {source_dir}")
        stats = normalize_source_directory(
            source_dir,
            canonical_metadata_dir=metadata_dir,
            session=session,
            search_limit=args.search_limit,
            min_similarity=args.min_similarity,
            dry_run=args.dry_run,
        )
        for key, value in stats.items():
            grand_total[key] += value
        print(
            f"- processed={stats['processed']} matched={stats['matched']} rewritten={stats['rewritten']} "
            f"promoted={stats['promoted']} duplicates={stats['duplicates']} unmatched={stats['unmatched']} invalid={stats['invalid']}"
        )

    print("Overall summary")
    print(
        f"- processed={grand_total['processed']} matched={grand_total['matched']} rewritten={grand_total['rewritten']} "
        f"promoted={grand_total['promoted']} duplicates={grand_total['duplicates']} unmatched={grand_total['unmatched']} invalid={grand_total['invalid']}"
    )


if __name__ == "__main__":
    main()
