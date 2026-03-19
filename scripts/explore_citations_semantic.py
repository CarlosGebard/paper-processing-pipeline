import json
import queue
import random
import sys
import threading
import time
from pathlib import Path

import requests


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_loader import get_config, get_env_or_config, get_pipeline_paths


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


existing_papers = {p.stem for p in papers_dir.glob("*.json")}
discarded_papers = {p.stem for p in discarded_dir.glob("*.json")}
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


def save_paper(paper):
    pid = paper["paperId"]
    file_path = papers_dir / f"{pid}.json"
    parent = seed

    if file_path.exists():
        with open(file_path) as f:
            data = json.load(f)
        parents = set(data.get("parent_papers", []))
        if parent in parents:
            return
        parents.add(parent)
        data["parent_papers"] = sorted(parents)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        return

    out = {
        "paperId": pid,
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
        "doi": paper.get("externalIds", {}).get("DOI"),
        "arxiv": paper.get("externalIds", {}).get("ArXiv"),
        "pdf_url": (paper.get("openAccessPdf") or {}).get("url"),
        "abstract": paper.get("abstract"),
        "parent_papers": [parent],
        "authors": [a["name"] for a in paper.get("authors", [])],
    }
    with open(file_path, "w") as f:
        json.dump(out, f, indent=2)


def save_discarded(paper):
    pid = paper["paperId"]
    out = {
        "paperId": pid,
        "title": paper.get("title"),
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount"),
    }
    with open(discarded_dir / f"{pid}.json", "w") as f:
        json.dump(out, f, indent=2)
    processed_papers.add(pid)


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
            p["abstract"] = abstract
            save_paper(p)
            accepted += 1
        elif decision == "n":
            save_discarded(p)
        elif decision == "q":
            break


if __name__ == "__main__":
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
