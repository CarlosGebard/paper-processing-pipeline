from __future__ import annotations

import json
import queue
import random
import threading
import time
from pathlib import Path
from typing import Any

import requests

from config_loader import get_config, get_env_or_config, get_pipeline_paths
from paper_pipeline.artifacts import build_base_name
from paper_pipeline.tools.paper_selector import PaperCandidate, classify_papers_with_openai


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

papers_dir.mkdir(parents=True, exist_ok=True)
discarded_dir.mkdir(parents=True, exist_ok=True)

session = requests.Session()
if SEMANTIC_API_KEY:
    session.headers.update({"x-api-key": SEMANTIC_API_KEY})

_rate_lock = threading.Lock()
_last_request_ts = 0.0
REQUEST_INTERVAL_SECONDS = 1.0


def _collect_processed_ids(directory: Path) -> set[str]:
    processed: set[str] = set()
    for path in directory.glob("*.json"):
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


existing_papers = _collect_processed_ids(papers_dir)
discarded_papers = _collect_processed_ids(discarded_dir)
processed_papers = existing_papers | discarded_papers


def _semantic_rate_limit():
    global _last_request_ts
    with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_request_ts
        if elapsed < REQUEST_INTERVAL_SECONDS:
            time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
        _last_request_ts = time.monotonic()


def request_with_backoff(url, params=None):
    retries = config["rate_limit"]["retries"]
    base_delay = config["rate_limit"]["base_delay"]
    max_delay = config["rate_limit"]["max_delay"]

    for attempt in range(retries):
        _semantic_rate_limit()
        r = session.get(url, params=params, timeout=60)

        if r.status_code == 200:
            return r

        if r.status_code in (429, 500, 502, 503, 504):
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay += random.uniform(0, 1)
            time.sleep(delay)
            continue

        r.raise_for_status()

    raise RuntimeError("Max retries exceeded")


def fetch_seed_metadata():
    url = f"{SEMANTIC_URL}/paper/{seed}"
    params = {"fields": "paperId,title,citationCount,year"}
    r = request_with_backoff(url, params=params)
    return r.json()


def truncate_abstract(text):
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
    parent: str,
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

    return {
        "paperId": paper["paperId"],
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
        "doi": external_ids.get("DOI"),
        "arxiv": external_ids.get("ArXiv"),
        "pdf_url": open_access_pdf.get("url"),
        "abstract": abstract_text,
        "parent_papers": [parent],
        "authors": [a["name"] for a in paper.get("authors", []) if isinstance(a, dict) and a.get("name")],
    }


def save_paper(paper):
    pid = paper["paperId"]
    doi = paper.get("externalIds", {}).get("DOI")
    file_stem = build_base_name(doi) if doi else pid
    file_path = papers_dir / f"{file_stem}.metadata.json"
    parent = seed

    if file_path.exists():
        data = json.loads(file_path.read_text(encoding="utf-8"))
        parents = set(data.get("parent_papers", []))
        if parent in parents:
            return
        parents.add(parent)
        data["parent_papers"] = sorted(parents)
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return

    out = paper_to_metadata_record(paper, parent=parent)
    file_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    processed_papers.add(pid)
    if doi:
        processed_papers.add(build_base_name(doi))


def save_discarded(paper, *, selection: dict[str, str] | None = None):
    pid = paper["paperId"]
    doi = paper.get("externalIds", {}).get("DOI")
    file_stem = build_base_name(doi) if doi else pid
    out = {
        "paperId": pid,
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
        "doi": doi,
        "arxiv": paper.get("externalIds", {}).get("ArXiv"),
    }
    if selection:
        out["selection"] = selection
    (discarded_dir / f"{file_stem}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    processed_papers.add(pid)
    if doi:
        processed_papers.add(build_base_name(doi))


def crawler_worker(paper_queue):
    offset = 0
    url = f"{SEMANTIC_URL}/paper/{seed}/citations"

    while True:
        params = {
            "fields": "citingPaper.paperId,title,year,authors,citationCount,externalIds,openAccessPdf,abstract",
            "limit": 100,
            "offset": offset,
        }
        r = request_with_backoff(url, params=params)
        data = r.json().get("data", [])
        if not data:
            break

        for entry in data:
            paper = entry.get("citingPaper", {})
            pid = paper.get("paperId")
            if not pid or pid in processed_papers:
                continue
            citation_count = paper.get("citationCount") or 0
            year = paper.get("year") or 0
            if citation_count < min_citations:
                continue
            if year < min_year:
                continue
            paper_queue.put(paper)
        offset += 100

    paper_queue.put(None)


def explore():
    paper_queue = queue.Queue(maxsize=buffer_size)
    crawler = threading.Thread(target=crawler_worker, args=(paper_queue,), daemon=True)
    crawler.start()

    accepted = 0
    while accepted < limit:
        p = paper_queue.get()
        if p is None:
            break

        abstract = truncate_abstract(p.get("abstract"))

        print("\n==============================")
        print("TITLE:", p.get("title"))
        print("YEAR:", p.get("year"))
        print("CITATIONS:", p.get("citationCount"))
        print("\nABSTRACT:\n")
        print(abstract if abstract else "No abstract found")
        print("==============================")

        decision = input("keep? (y/n/q): ").lower().strip()
        if decision == "y":
            save_paper(p)
            accepted += 1
        elif decision == "n":
            save_discarded(p)
        elif decision == "q":
            break


def _build_paper_candidate(index: int, paper: dict[str, Any]) -> PaperCandidate:
    return PaperCandidate(
        id=f"cand_{index:03d}",
        title=str(paper.get("title") or "").strip() or "Untitled paper",
        abstract_preview=build_selection_preview(paper.get("abstract"), max_words=selection_preview_words),
    )


def _process_selection_batch(
    batch: list[dict[str, Any]],
    accepted: int,
    accepted_limit: int,
) -> tuple[int, bool, int, int, int]:
    if not batch:
        return accepted, False, 0, 0, 0

    candidates = [_build_paper_candidate(index + 1, paper) for index, paper in enumerate(batch)]
    decisions, _raw_response = classify_papers_with_openai(
        candidates=candidates,
        model=selection_model,
    )
    decisions_by_id = {item["id"]: item for item in decisions}
    processed_count = 0
    kept_count = 0
    dropped_count = 0

    for candidate, paper in zip(candidates, batch):
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
                selection={
                    "mode": "nutrition-rag",
                    "decision": decision["decision"],
                    "reason": reason,
                    "preview": preview,
                },
            )
            dropped_count += 1
            continue

        if accepted >= accepted_limit:
            return accepted, True, processed_count - 1, kept_count, dropped_count

        print(f"[KEEP] {title}")
        print(f"  preview: {preview}")
        print(f"  reason: {reason}")
        save_paper(paper)
        accepted += 1
        kept_count += 1

    return accepted, accepted >= accepted_limit, processed_count, kept_count, dropped_count


def explore_with_nutrition_rag() -> None:
    paper_queue = queue.Queue(maxsize=buffer_size)
    crawler = threading.Thread(target=crawler_worker, args=(paper_queue,), daemon=True)
    crawler.start()

    accepted = 0
    reviewed = 0
    dropped = 0
    batch: list[dict[str, Any]] = []
    exhausted = False

    while accepted < limit:
        paper = paper_queue.get()
        if paper is None:
            exhausted = True
            break
        batch.append(paper)
        if len(batch) < selection_batch_size:
            continue

        accepted, reached_limit, processed_count, _kept_count, dropped_count = _process_selection_batch(batch, accepted, limit)
        reviewed += processed_count
        dropped += dropped_count
        batch = []
        if reached_limit:
            break

    if batch and accepted < limit:
        accepted, _reached_limit, processed_count, _kept_count, dropped_count = _process_selection_batch(batch, accepted, limit)
        reviewed += processed_count
        dropped += dropped_count

    print("\nResumen metadata nutrition-rag")
    print(f"- Modelo OpenAI:          {selection_model}")
    print(f"- Preview abstract words: {selection_preview_words}")
    print(f"- Batch size:             {selection_batch_size}")
    print(f"- Reviewed:               {reviewed}")
    print(f"- Kept:                   {accepted}")
    print(f"- Dropped:                {dropped}")
    print(f"- Source exhausted:       {'yes' if exhausted else 'no'}")


def run_interactive_exploration() -> None:
    try:
        seed_meta = fetch_seed_metadata()
    except Exception as exc:
        raise SystemExit(f"Seed inválido o no encontrado: {seed}. Error: {exc}")

    print("\nSeed:", seed)
    print("Seed detected:", seed_meta.get("title", "Unknown title"))
    print("Seed citations:", seed_meta.get("citationCount", 0))
    print("Minimum citations:", min_citations)
    print("Minimum year:", min_year)
    print("Max abstract words:", max_words)
    print("Semantic Scholar rate limit:", "1 request/second")
    print()

    explore()


def run_nutrition_rag_exploration() -> None:
    try:
        seed_meta = fetch_seed_metadata()
    except Exception as exc:
        raise SystemExit(f"Seed inválido o no encontrado: {seed}. Error: {exc}")

    print("\nSeed:", seed)
    print("Seed detected:", seed_meta.get("title", "Unknown title"))
    print("Seed citations:", seed_meta.get("citationCount", 0))
    print("Minimum citations:", min_citations)
    print("Minimum year:", min_year)
    print("Selection mode:", "nutrition-rag")
    print("Preview abstract words:", selection_preview_words)
    print("Selection batch size:", selection_batch_size)
    print("Semantic Scholar rate limit:", "1 request/second")
    print()

    explore_with_nutrition_rag()


if __name__ == "__main__":
    run_interactive_exploration()
