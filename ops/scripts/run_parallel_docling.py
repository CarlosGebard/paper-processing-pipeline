#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_WORKERS = 4
DEFAULT_MEMORY_GB_PER_WORKER = 6.0

import config_loader as ctx
from paper_pipeline.artifacts import parse_document_from_pdf_name, refresh_registry_record
from paper_pipeline.stages.pdfs import list_pdf_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta Docling + heuristics en paralelo como opcion externa."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Cantidad de workers paralelos para PDFs pendientes.",
    )
    parser.add_argument(
        "--memory-gb-per-worker",
        type=float,
        default=DEFAULT_MEMORY_GB_PER_WORKER,
        help="Memoria estimada por worker Docling para limitar concurrencia segun RAM disponible.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita la cantidad de PDFs pendientes a procesar.",
    )
    return parser.parse_args()


def discover_pending_pdfs(limit: int | None = None) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []

    for pdf_path in list_pdf_candidates():
        document_id, doi, base_name = parse_document_from_pdf_name(pdf_path)
        record = refresh_registry_record(document_id, doi, base_name)
        stage_status = record.get("stage_status", {})

        if stage_status.get("completed"):
            print(f"[SKIP COMPLETE] {pdf_path.name}")
            continue

        if stage_status.get("heuristics"):
            print(f"[SKIP HEURISTICS] {pdf_path.name}")
            continue

        pending.append(
            {
                "pdf_path": pdf_path,
                "document_id": document_id,
                "doi": doi,
                "base_name": base_name,
            }
        )

        if limit is not None and len(pending) >= limit:
            break

    return pending


def process_one(entry: dict[str, Any]) -> dict[str, Any]:
    runner = ctx.resolve_docling_v2_pipeline_runner()
    result = runner(
        input_pdf=entry["pdf_path"],
        output_root_dir=ctx.DOCLING_HEURISTICS_DIR,
        metadata_dir=ctx.METADATA_DIR,
        dotenv_path=ctx.ROOT_DIR / ".env",
        document_id=entry["document_id"],
        doi=entry["doi"],
        base_name=entry["base_name"],
    )
    return {
        "document_id": entry["document_id"],
        "doi": entry["doi"],
        "base_name": entry["base_name"],
        "pdf_path": entry["pdf_path"],
        "result": result,
    }


def read_available_memory_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return int(parts[1]) * 1024

    if hasattr(os, "sysconf"):
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            available_pages = os.sysconf("SC_AVPHYS_PAGES")
            if isinstance(page_size, int) and isinstance(available_pages, int):
                return page_size * available_pages
        except (OSError, ValueError):
            return None

    return None


def determine_effective_workers(requested_workers: int, memory_gb_per_worker: float) -> tuple[int, str | None]:
    if requested_workers < 1:
        raise ValueError("--workers debe ser >= 1")
    if memory_gb_per_worker <= 0:
        raise ValueError("--memory-gb-per-worker debe ser > 0")

    available_bytes = read_available_memory_bytes()
    if available_bytes is None:
        return requested_workers, None

    memory_bytes_per_worker = int(memory_gb_per_worker * 1024**3)
    if memory_bytes_per_worker <= 0:
        return requested_workers, None

    memory_limited_workers = max(1, available_bytes // memory_bytes_per_worker)
    effective_workers = max(1, min(requested_workers, memory_limited_workers))

    if effective_workers == requested_workers:
        return effective_workers, None

    available_gb = available_bytes / 1024**3
    note = (
        f"Ajustando workers de {requested_workers} a {effective_workers} "
        f"por RAM disponible (~{available_gb:.1f} GiB, {memory_gb_per_worker:.1f} GiB/worker)."
    )
    return effective_workers, note


def handle_future_result(future: Future[dict[str, Any]], entry: dict[str, Any]) -> tuple[int, int]:
    ok_count = 0
    fail_count = 0
    pdf_path = Path(entry["pdf_path"])
    try:
        payload = future.result()
        refresh_registry_record(
            payload["document_id"],
            payload["doi"],
            payload["base_name"],
        )
        ok_count += 1
        result = payload["result"]
        print(f"[OK] {pdf_path.name}")
        print(f"  - Output dir:    {ctx.display_path(Path(result['output_dir']))}")
        print(f"  - Docling JSON:  {ctx.display_path(Path(result['json_path']))}")
        print(f"  - Filtered JSON: {ctx.display_path(Path(result['filtered_json_path']))}")
        print(f"  - Final JSON:    {ctx.display_path(Path(result['final_json_path']))}")
    except Exception as exc:
        fail_count += 1
        print(f"[FAIL] {pdf_path.name}: {exc}")
    return ok_count, fail_count


def process_pending_pdfs(pending: list[dict[str, Any]], workers: int) -> tuple[int, int]:
    ok_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending_iter = iter(pending)
        futures: dict[Future[dict[str, Any]], dict[str, Any]] = {}

        for _ in range(min(workers, len(pending))):
            entry = next(pending_iter, None)
            if entry is None:
                break
            futures[executor.submit(process_one, entry)] = entry

        while futures:
            done, _not_done = wait(futures, return_when=FIRST_COMPLETED)

            for future in done:
                entry = futures.pop(future)
                ok_delta, fail_delta = handle_future_result(future, entry)
                ok_count += ok_delta
                fail_count += fail_delta

                next_entry = next(pending_iter, None)
                if next_entry is not None:
                    futures[executor.submit(process_one, next_entry)] = next_entry

    return ok_count, fail_count


def main() -> None:
    args = parse_args()
    effective_workers, note = determine_effective_workers(
        args.workers,
        args.memory_gb_per_worker,
    )

    ctx.ensure_dirs()
    pending = discover_pending_pdfs(limit=args.limit)

    if not pending:
        print(f"No hay PDFs pendientes en {ctx.display_path(ctx.DOCLING_INPUT_DIR)}.")
        return

    print(f"Pendientes: {len(pending)}")
    print(f"Workers:    {effective_workers}")
    if note:
        print(f"[RAM GUARD] {note}")

    ok_count, fail_count = process_pending_pdfs(pending, effective_workers)

    print("\nResumen parallel-docling")
    print(f"- Pendientes procesados: {len(pending)}")
    print(f"- Exitosos:              {ok_count}")
    print(f"- Fallidos:              {fail_count}")


if __name__ == "__main__":
    main()
