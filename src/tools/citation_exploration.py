from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import requests
from requests import HTTPError

from src.config import (
    EXPLORATION_COMPLETED_SEED_DOI_FILE,
    EXPLORATION_SEED_DOI_FILE,
    get_config,
    get_env_or_config,
    get_pipeline_paths,
)
from src.artifacts import build_base_name, normalize_doi
from src.tools.paper_selector import PaperCandidate, classify_papers_with_openai


config = get_config()
paths = get_pipeline_paths(config)

SEMANTIC_URL = config["api"]["semantic_scholar_url"]
SEMANTIC_API_KEY = get_env_or_config(
    "SEMANTIC_SCHOLAR_API_KEY",
    "api",
    "semantic_scholar_api_key",
    config=config,
)

seed = config["seed_paper"]
seed_doi_file = EXPLORATION_SEED_DOI_FILE
completed_seed_doi_file = EXPLORATION_COMPLETED_SEED_DOI_FILE

limit = config["exploration"]["limit"]
min_citations = config["exploration"]["min_citations"]
buffer_size = config["exploration"]["buffer_size"]
max_words = config["exploration"]["max_abstract_words"]
min_year = config["exploration"].get("min_year", 2000)
metadata_selection_cfg = config.get("metadata_selection") or {}
selection_model = get_env_or_config(
    "OPENAI_METADATA_SELECTION_MODEL",
    "metadata_selection",
    "model",
    default="gpt-5-mini",
    config=config,
)
selection_preview_words = max(1, int(metadata_selection_cfg.get("abstract_preview_words", 20)))
selection_batch_size = max(1, int(metadata_selection_cfg.get("batch_size", 20)))

papers_dir = paths["metadata_dir"]
discarded_dir = paths["discarded_dir"]

session = requests.Session()
if SEMANTIC_API_KEY:
    session.headers.update({"x-api-key": SEMANTIC_API_KEY})

_rate_lock = threading.Lock()
_last_request_ts = 0.0
REQUEST_INTERVAL_SECONDS = 1.0
PAPER_FIELDS = "paperId,title,year,authors,citationCount,externalIds,openAccessPdf,abstract"
CITATION_FIELDS = f"citingPaper.{PAPER_FIELDS}"


def normalize_selection_mode(selection_mode: str) -> str:
    normalized = str(selection_mode or "").strip()
    if normalized in {"broad-nutrition", "nutrition-rag"}:
        return "broad-nutrition"
    if normalized in {"undercovered-topics", "gap-rag"}:
        return "undercovered-topics"
    raise ValueError(f"Selection mode no soportado: {selection_mode}")


def _collect_processed_ids(directory: Path) -> set[str]:
    processed: set[str] = set()
    for path in directory.rglob("*.json"):
        processed.add(path.stem)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        paper_id = str(payload.get("paperId") or "").strip()
        doi = str(payload.get("doi") or "").strip()
        if paper_id:
            processed.add(paper_id)
        if doi:
            processed.add(build_base_name(doi))
    return processed


def collect_processed_papers() -> set[str]:
    return _collect_processed_ids(papers_dir) | _collect_processed_ids(discarded_dir)


def _today_bucket_name() -> str:
    return datetime.now().date().isoformat()


def _gap_rag_discarded_dir(bucket_name: str | None = None) -> Path:
    return discarded_dir / "gap-rag" / (bucket_name or _today_bucket_name())


def _resolve_existing_discarded_path(file_stem: str) -> Path | None:
    legacy_path = discarded_dir / f"{file_stem}.json"
    if legacy_path.exists():
        return legacy_path

    matches = sorted(discarded_dir.rglob(f"{file_stem}.json"))
    if matches:
        return matches[0]
    return None


def _discard_destination_path(file_stem: str, selection: dict[str, str] | None) -> Path:
    existing = _resolve_existing_discarded_path(file_stem)
    if existing is not None:
        return existing

    selection_mode = str((selection or {}).get("mode") or "").strip()
    if selection_mode and normalize_selection_mode(selection_mode) == "undercovered-topics":
        return _gap_rag_discarded_dir() / f"{file_stem}.json"
    return discarded_dir / f"{file_stem}.json"


def _semantic_rate_limit() -> None:
    global _last_request_ts
    with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_request_ts
        if elapsed < REQUEST_INTERVAL_SECONDS:
            time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
        _last_request_ts = time.monotonic()


def request_with_backoff(url: str, params: dict[str, Any] | None = None) -> requests.Response:
    retries = config["rate_limit"]["retries"]
    base_delay = config["rate_limit"]["base_delay"]
    max_delay = config["rate_limit"]["max_delay"]

    for attempt in range(retries):
        _semantic_rate_limit()
        response = session.get(url, params=params, timeout=60)

        if response.status_code == 200:
            return response

        if response.status_code in (429, 500, 502, 503, 504):
            delay = min(max_delay, base_delay * (2**attempt))
            delay += random.uniform(0, 1)
            time.sleep(delay)
            continue

        response.raise_for_status()

    raise RuntimeError("Max retries exceeded")


def fetch_paper_by_doi(doi: str) -> dict[str, Any]:
    normalized_doi = normalize_doi(doi)
    url = f"{SEMANTIC_URL}/paper/DOI:{normalized_doi}"
    response = request_with_backoff(url, params={"fields": PAPER_FIELDS})
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("paperId"):
        raise RuntimeError(f"Seed DOI inválido o no encontrado: {normalized_doi}")
    return payload


def _load_doi_list(doi_file: Path) -> list[str]:
    seeds: list[str] = []
    seen: set[str] = set()

    if doi_file.exists():
        for raw_line in doi_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            normalized = normalize_doi(line)
            if normalized and normalized not in seen:
                seeds.append(normalized)
                seen.add(normalized)

    return seeds


def load_seed_dois(
    doi_file: Path = seed_doi_file,
    fallback_seed: str | None = seed,
) -> list[str]:
    seeds = _load_doi_list(doi_file)

    if seeds:
        return seeds

    if doi_file.exists():
        return []

    if fallback_seed:
        normalized_seed = normalize_doi(fallback_seed)
        if normalized_seed:
            return [normalized_seed]

    raise ValueError(
        f"No se encontraron seed DOIs en {doi_file} y no hay fallback configurado."
    )


def load_completed_seed_dois(doi_file: Path = completed_seed_doi_file) -> set[str]:
    return set(_load_doi_list(doi_file))


def _remove_seed_doi_from_queue(doi: str, doi_file: Path) -> None:
    if not doi_file.exists():
        return

    normalized = normalize_doi(doi)
    kept_lines: list[str] = []

    for raw_line in doi_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and normalize_doi(line) == normalized:
            continue
        kept_lines.append(raw_line)

    content = "\n".join(kept_lines)
    if kept_lines:
        content += "\n"
    doi_file.write_text(content, encoding="utf-8")


def sync_seed_doi_queue(
    *,
    source_doi_file: Path = seed_doi_file,
    completed_doi_file: Path = completed_seed_doi_file,
) -> None:
    completed_dois = load_completed_seed_dois(completed_doi_file)
    if not completed_dois or not source_doi_file.exists():
        return

    for doi in completed_dois:
        _remove_seed_doi_from_queue(doi, source_doi_file)


def append_completed_seed_doi(
    doi: str,
    doi_file: Path = completed_seed_doi_file,
    *,
    source_doi_file: Path | None = seed_doi_file,
) -> None:
    normalized = normalize_doi(doi)
    existing = load_completed_seed_dois(doi_file)
    if normalized in existing:
        if source_doi_file is not None:
            _remove_seed_doi_from_queue(normalized, source_doi_file)
        return
    doi_file.parent.mkdir(parents=True, exist_ok=True)
    with doi_file.open("a", encoding="utf-8") as fh:
        fh.write(f"{normalized}\n")
    if source_doi_file is not None:
        _remove_seed_doi_from_queue(normalized, source_doi_file)


def truncate_abstract(text: str | None) -> str | None:
    if not text:
        return None
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def build_selection_preview(text: str | None, max_words: int = selection_preview_words) -> str:
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + "..."


def paper_to_metadata_record(
    paper: dict[str, Any],
    *,
    parent: str | None,
    seed_doi: str | None = None,
    is_seed_paper: bool = False,
    abstract_word_limit: int = max_words,
) -> dict[str, Any]:
    abstract_text = str(paper.get("abstract") or "").strip()
    if abstract_text:
        words = abstract_text.split()
        if len(words) > abstract_word_limit:
            abstract_text = " ".join(words[:abstract_word_limit]) + "..."
    else:
        abstract_text = None

    external_ids = paper.get("externalIds") or {}
    open_access_pdf = paper.get("openAccessPdf") or {}
    normalized_seed_doi = normalize_doi(seed_doi) if seed_doi else None

    return {
        "paperId": paper["paperId"],
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
        "doi": external_ids.get("DOI"),
        "arxiv": external_ids.get("ArXiv"),
        "pdf_url": open_access_pdf.get("url"),
        "abstract": abstract_text,
        "parent_papers": [parent] if parent else [],
        "seed_papers": [normalized_seed_doi] if normalized_seed_doi else [],
        "is_seed_paper": is_seed_paper,
        "authors": [a["name"] for a in paper.get("authors", []) if isinstance(a, dict) and a.get("name")],
    }


def _paper_file_stem(paper: dict[str, Any]) -> str:
    doi = str((paper.get("externalIds") or {}).get("DOI") or "").strip()
    paper_id = str(paper.get("paperId") or "").strip()
    if doi:
        return build_base_name(doi)
    if paper_id:
        return paper_id
    raise ValueError("Paper sin DOI ni paperId.")


def _merge_metadata_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key in ("paperId", "title", "year", "citationCount", "doi", "arxiv", "pdf_url", "abstract"):
        if incoming.get(key) not in (None, ""):
            merged[key] = incoming.get(key)

    merged["authors"] = sorted(
        {
            str(author).strip()
            for author in [*(existing.get("authors") or []), *(incoming.get("authors") or [])]
            if str(author).strip()
        }
    )
    merged["parent_papers"] = sorted(
        {
            str(parent).strip()
            for parent in [*(existing.get("parent_papers") or []), *(incoming.get("parent_papers") or [])]
            if str(parent).strip()
        }
    )
    merged["seed_papers"] = sorted(
        {
            normalize_doi(str(seed_doi))
            for seed_doi in [*(existing.get("seed_papers") or []), *(incoming.get("seed_papers") or [])]
            if str(seed_doi).strip()
        }
    )
    merged["is_seed_paper"] = bool(existing.get("is_seed_paper")) or bool(incoming.get("is_seed_paper"))
    return merged


def _discard_file_payload(
    paper: dict[str, Any],
    *,
    seed_doi: str | None = None,
    selection: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        "paperId": paper["paperId"],
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
        "doi": (paper.get("externalIds") or {}).get("DOI"),
        "arxiv": (paper.get("externalIds") or {}).get("ArXiv"),
        "seed_papers": [normalize_doi(seed_doi)] if seed_doi else [],
    }
    if selection:
        payload["selection"] = selection
    return payload


def _merge_discarded_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key in ("paperId", "title", "year", "citationCount", "doi", "arxiv"):
        if incoming.get(key) not in (None, ""):
            merged[key] = incoming.get(key)

    merged["seed_papers"] = sorted(
        {
            normalize_doi(str(seed_doi))
            for seed_doi in [*(existing.get("seed_papers") or []), *(incoming.get("seed_papers") or [])]
            if str(seed_doi).strip()
        }
    )
    if "selection" in incoming:
        merged["selection"] = incoming["selection"]
    return merged


def _record_identifiers(record: dict[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    paper_id = str(record.get("paperId") or "").strip()
    doi = str(record.get("doi") or "").strip()
    if paper_id:
        identifiers.add(paper_id)
    if doi:
        identifiers.add(build_base_name(doi))
    return identifiers


def _ensure_parent_saved(
    parent: str | None,
    *,
    parent_paper: dict[str, Any] | None = None,
    seed_doi: str | None = None,
    processed_papers: set[str] | None = None,
) -> None:
    if not parent or parent_paper is None:
        return
    if processed_papers is not None and parent in processed_papers:
        return
    save_paper(
        parent_paper,
        parent=None,
        seed_doi=seed_doi,
        is_seed_paper=False,
        processed_papers=processed_papers,
    )


def save_paper(
    paper: dict[str, Any],
    *,
    parent: str | None,
    parent_paper: dict[str, Any] | None = None,
    seed_doi: str | None = None,
    is_seed_paper: bool = False,
    processed_papers: set[str] | None = None,
) -> None:
    _ensure_parent_saved(
        parent,
        parent_paper=parent_paper,
        seed_doi=seed_doi,
        processed_papers=processed_papers,
    )
    file_stem = _paper_file_stem(paper)
    file_path = papers_dir / f"{file_stem}.metadata.json"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    incoming = paper_to_metadata_record(
        paper,
        parent=parent,
        seed_doi=seed_doi,
        is_seed_paper=is_seed_paper,
    )

    if file_path.exists():
        existing = json.loads(file_path.read_text(encoding="utf-8"))
        incoming = _merge_metadata_record(existing, incoming)

    file_path.write_text(json.dumps(incoming, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if processed_papers is not None:
        processed_papers.update(_record_identifiers(incoming))


def save_discarded(
    paper: dict[str, Any],
    *,
    parent: str | None = None,
    parent_paper: dict[str, Any] | None = None,
    seed_doi: str | None = None,
    selection: dict[str, str] | None = None,
    processed_papers: set[str] | None = None,
) -> None:
    _ensure_parent_saved(
        parent,
        parent_paper=parent_paper,
        seed_doi=seed_doi,
        processed_papers=processed_papers,
    )
    file_stem = _paper_file_stem(paper)
    file_path = _discard_destination_path(file_stem, selection)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    incoming = _discard_file_payload(paper, seed_doi=seed_doi, selection=selection)

    if file_path.exists():
        existing = json.loads(file_path.read_text(encoding="utf-8"))
        incoming = _merge_discarded_record(existing, incoming)

    file_path.write_text(json.dumps(incoming, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if processed_papers is not None:
        processed_papers.update(_record_identifiers(incoming))


def _paper_storage_state(paper: dict[str, Any]) -> str | None:
    file_stem = _paper_file_stem(paper)
    if (papers_dir / f"{file_stem}.metadata.json").exists():
        return "kept"
    if _resolve_existing_discarded_path(file_stem) is not None:
        return "discarded"
    return None


def iter_seed_citations(seed_paper: dict[str, Any]) -> Iterator[dict[str, Any]]:
    offset = 0
    url = f"{SEMANTIC_URL}/paper/{seed_paper['paperId']}/citations"

    while True:
        params = {
            "fields": CITATION_FIELDS,
            "limit": 100,
            "offset": offset,
        }
        response = request_with_backoff(url, params=params)
        data = response.json().get("data", [])
        if not data:
            break

        for entry in data:
            paper = entry.get("citingPaper", {})
            paper_id = paper.get("paperId")
            if not paper_id:
                continue
            citation_count = paper.get("citationCount") or 0
            year = paper.get("year") or 0
            if citation_count < min_citations:
                continue
            if year < min_year:
                continue
            yield paper
        offset += 100


def _build_paper_candidate(index: int, paper: dict[str, Any]) -> PaperCandidate:
    return PaperCandidate(
        id=f"cand_{index:03d}",
        title=str(paper.get("title") or "").strip() or "Untitled paper",
        abstract_preview=build_selection_preview(paper.get("abstract"), max_words=selection_preview_words),
    )


def _process_selection_batch(
    batch: list[dict[str, Any]],
    accepted: int,
    *,
    processed_papers: set[str],
    selection_mode: str = "broad-nutrition",
) -> tuple[int, int, int, int]:
    if not batch:
        return accepted, 0, 0, 0

    normalized_mode = normalize_selection_mode(selection_mode)
    candidates = [_build_paper_candidate(index + 1, item["paper"]) for index, item in enumerate(batch)]
    decisions, _raw_response = classify_papers_with_openai(
        candidates=candidates,
        model=selection_model,
        selection_profile=normalized_mode,
    )
    decisions_by_id = {item["id"]: item for item in decisions}
    processed_count = 0
    kept_count = 0
    dropped_count = 0

    for candidate, item in zip(candidates, batch):
        paper = item["paper"]
        seed_doi = item["seed_doi"]
        parent = item["parent"]
        parent_paper = item.get("parent_paper")
        decision = decisions_by_id.get(
            candidate.id,
            {"decision": "uncertain", "reason": "missing_decision"},
        )
        processed_count += 1
        preview = candidate.abstract_preview or "No abstract preview available."
        title = candidate.title
        reason = decision["reason"]

        if decision["decision"] == "drop":
            print(f"[DROP] {title}")
            print(f"  preview: {preview}")
            print(f"  reason: {reason}")
            save_discarded(
                paper,
                parent=parent,
                parent_paper=parent_paper,
                seed_doi=seed_doi,
                selection={
                    "mode": selection_mode,
                    "profile": normalized_mode,
                    "decision": decision["decision"],
                    "reason": reason,
                    "preview": preview,
                },
                processed_papers=processed_papers,
            )
            dropped_count += 1
            continue

        print(f"[KEEP] {title}")
        print(f"  preview: {preview}")
        print(f"  reason: {reason}")
        save_paper(
            paper,
            parent=parent,
            parent_paper=parent_paper,
            seed_doi=seed_doi,
            processed_papers=processed_papers,
        )
        accepted += 1
        kept_count += 1

    return accepted, processed_count, kept_count, dropped_count


def explore_with_llm_selection(
    *,
    seed_dois: list[str] | None = None,
    selection_mode: str,
    summary_label: str,
) -> None:
    normalized_mode = normalize_selection_mode(selection_mode)
    if seed_dois is None:
        sync_seed_doi_queue()
    resolved_seed_dois = seed_dois or load_seed_dois()
    completed_seed_dois = load_completed_seed_dois()
    pending_seed_dois = [seed_doi for seed_doi in resolved_seed_dois if seed_doi not in completed_seed_dois]
    processed_papers = collect_processed_papers()
    accepted = 0
    reviewed = 0
    dropped = 0
    existing = 0
    skipped_seed_errors = 0
    skipped_completed = len(resolved_seed_dois) - len(pending_seed_dois)
    batch: list[dict[str, Any]] = []
    exhausted = True

    for seed_doi in pending_seed_dois:
        try:
            seed_paper = fetch_paper_by_doi(seed_doi)
        except HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                print(f"[SEED SKIP] {seed_doi} -> not found in Semantic Scholar")
                append_completed_seed_doi(seed_doi)
                skipped_seed_errors += 1
                continue
            raise
        save_paper(
            seed_paper,
            parent=None,
            seed_doi=seed_doi,
            is_seed_paper=True,
            processed_papers=processed_papers,
        )
        print(f"[SEED] {seed_doi} -> {seed_paper.get('title') or 'Unknown title'}")

        for paper in iter_seed_citations(seed_paper):
            state = _paper_storage_state(paper)
            if state == "kept":
                save_paper(
                    paper,
                    parent=seed_paper["paperId"],
                    seed_doi=seed_doi,
                    processed_papers=processed_papers,
                )
                existing += 1
                continue
            if state == "discarded":
                save_discarded(
                    paper,
                    seed_doi=seed_doi,
                    processed_papers=processed_papers,
                )
                existing += 1
                continue

            batch.append(
                {
                    "paper": paper,
                    "seed_doi": seed_doi,
                    "parent": seed_paper["paperId"],
                    "parent_paper": seed_paper,
                }
            )
            if len(batch) < selection_batch_size:
                continue

            accepted, processed_count, _kept_count, dropped_count = _process_selection_batch(
                batch,
                accepted,
                processed_papers=processed_papers,
                selection_mode=normalized_mode,
            )
            reviewed += processed_count
            dropped += dropped_count
            batch = []

        if batch:
            accepted, processed_count, _kept_count, dropped_count = _process_selection_batch(
                batch,
                accepted,
                processed_papers=processed_papers,
                selection_mode=normalized_mode,
            )
            reviewed += processed_count
            dropped += dropped_count
            batch = []

        append_completed_seed_doi(seed_doi)

    if batch:
        accepted, processed_count, _kept_count, dropped_count = _process_selection_batch(
            batch,
            accepted,
            processed_papers=processed_papers,
            selection_mode=normalized_mode,
        )
        reviewed += processed_count
        dropped += dropped_count

    print(f"\nResumen metadata {summary_label}")
    print(f"- Modelo OpenAI:          {selection_model}")
    print(f"- Seed DOI file:          {seed_doi_file}")
    print(f"- Seed DOIs loaded:       {len(resolved_seed_dois)}")
    print(f"- Seed DOI done file:     {completed_seed_doi_file}")
    print(f"- Seed DOIs pending:      {len(pending_seed_dois)}")
    print(f"- Seed DOIs completed:    {skipped_completed}")
    print(f"- Seed DOIs skipped:      {skipped_seed_errors}")
    print(f"- Preview abstract words: {selection_preview_words}")
    print(f"- Batch size:             {selection_batch_size}")
    print(f"- Reviewed:               {reviewed}")
    print(f"- Existing merged:        {existing}")
    print(f"- Kept:                   {accepted}")
    print(f"- Dropped:                {dropped}")
    print(f"- Source exhausted:       {'yes' if exhausted else 'no'}")


def explore_with_nutrition_rag(seed_dois: list[str] | None = None) -> None:
    explore_with_llm_selection(
        seed_dois=seed_dois,
        selection_mode="broad-nutrition",
        summary_label="broad-nutrition",
    )


def explore_with_gap_rag(seed_dois: list[str] | None = None) -> None:
    explore_with_llm_selection(
        seed_dois=seed_dois,
        selection_mode="undercovered-topics",
        summary_label="undercovered-topics",
    )


def run_nutrition_rag_exploration() -> None:
    _run_llm_selection_exploration("broad-nutrition")


def run_gap_rag_exploration() -> None:
    _run_llm_selection_exploration("undercovered-topics")


def _run_llm_selection_exploration(selection_mode: str) -> None:
    normalized_mode = normalize_selection_mode(selection_mode)
    try:
        sync_seed_doi_queue()
        resolved_seed_dois = load_seed_dois()
        completed_seed_dois = load_completed_seed_dois()
        pending_seed_dois = [seed_doi for seed_doi in resolved_seed_dois if seed_doi not in completed_seed_dois]
        if not pending_seed_dois:
            print(f"\nSelection mode: {normalized_mode}")
            print("Seed DOI file:", seed_doi_file)
            print("Seed DOI done file:", completed_seed_doi_file)
            print("Seed DOIs loaded:", len(resolved_seed_dois))
            print("Seed DOIs pending:", 0)
            print("No pending seed DOIs to process.")
            return
    except Exception as exc:
        raise SystemExit(f"Seed DOI inválido o no encontrado. Error: {exc}")

    print("\nSelection mode:", normalized_mode)
    print("Seed DOI file:", seed_doi_file)
    print("Seed DOI done file:", completed_seed_doi_file)
    print("Seed DOIs loaded:", len(resolved_seed_dois))
    print("Seed DOIs pending:", len(pending_seed_dois))
    print("First pending seed:", pending_seed_dois[0])
    print("Minimum citations:", min_citations)
    print("Minimum year:", min_year)
    print("Preview abstract words:", selection_preview_words)
    print("Selection batch size:", selection_batch_size)
    print("Semantic Scholar rate limit:", "1 request/second")
    print()

    if normalized_mode == "broad-nutrition":
        explore_with_nutrition_rag(pending_seed_dois)
        return
    if normalized_mode == "undercovered-topics":
        explore_with_gap_rag(pending_seed_dois)
        return
    raise ValueError(f"Selection mode no soportado: {selection_mode}")


if __name__ == "__main__":
    run_nutrition_rag_exploration()
