#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx
from src.tools.paper_selector import PaperCandidate, classify_papers_with_openai


CONFIG = ctx.get_config()
PATHS = ctx.get_pipeline_paths(CONFIG)
METADATA_SELECTION_CFG = CONFIG.get("metadata_selection") or {}
DEFAULT_MODEL = ctx.get_env_or_config(
    "OPENAI_METADATA_SELECTION_MODEL",
    "metadata_selection",
    "model",
    default="gpt-5-mini",
    config=CONFIG,
)
DEFAULT_BATCH_SIZE = max(1, int(METADATA_SELECTION_CFG.get("batch_size", 20)))
DEFAULT_PREVIEW_WORDS = max(1, int(METADATA_SELECTION_CFG.get("abstract_preview_words", 20)))
DEFAULT_STATE_FILE = ctx.DATA_RUNTIME_DIR / "refilter_metadata_with_paper_selector.state.json"
DEFAULT_SUMMARY_FILE = ctx.DATA_RUNTIME_DIR / "refilter_metadata_with_paper_selector.summary.json"


@dataclass
class MetadataCandidate:
    id: str
    path: Path
    metadata: dict[str, Any]
    candidate: PaperCandidate


def metadata_section(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    section = payload.get("metadata")
    if isinstance(section, dict):
        return section
    return payload


def build_preview(text: str | None, *, max_words: int) -> str:
    if not text:
        return ""
    words = str(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + "..."


def load_metadata_candidate(path: Path, *, preview_words: int) -> MetadataCandidate | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    metadata = metadata_section(payload)
    if not metadata:
        return None

    title = str(metadata.get("title") or "").strip()
    if not title:
        return None

    base_name = path.name.removesuffix(".metadata.json")
    preview = build_preview(str(metadata.get("abstract") or "").strip(), max_words=preview_words)
    return MetadataCandidate(
        id=base_name,
        path=path,
        metadata=metadata,
        candidate=PaperCandidate(
            id=base_name,
            title=title,
            abstract_preview=preview,
        ),
    )


def iter_metadata_candidates(metadata_dir: Path, *, preview_words: int) -> list[MetadataCandidate]:
    candidates: list[MetadataCandidate] = []
    if not metadata_dir.exists():
        return candidates

    for path in sorted(metadata_dir.glob("*.metadata.json")):
        candidate = load_metadata_candidate(path, preview_words=preview_words)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def batched(items: list[MetadataCandidate], size: int) -> Iterable[list[MetadataCandidate]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def classify_metadata_candidates(
    candidates: list[MetadataCandidate],
    *,
    model: str,
) -> dict[str, dict[str, str]]:
    decisions_by_id: dict[str, dict[str, str]] = {}
    decisions, _response_json = classify_papers_with_openai(
        [item.candidate for item in candidates],
        model=model,
    )
    for decision in decisions:
        decisions_by_id[decision["id"]] = decision
    return decisions_by_id


def build_discarded_payload(candidate: MetadataCandidate, decision: dict[str, str]) -> dict[str, Any]:
    payload = dict(candidate.metadata)
    payload["selection"] = {
        "decision": decision["decision"],
        "reason": decision["reason"],
        "source": "refilter_metadata_with_paper_selector",
    }
    payload["source_metadata_file"] = candidate.path.name
    return payload


def load_state(state_file: Path, *, reset_state: bool) -> dict[str, Any]:
    if reset_state or not state_file.exists():
        return {
            "completed": False,
            "reviewed_count": 0,
            "kept_count": 0,
            "dropped_count": 0,
            "uncertain_count": 0,
            "invalid_count": 0,
            "processed_ids": [],
            "newly_rejected": [],
        }
    return json.loads(state_file.read_text(encoding="utf-8"))


def persist_state(state_file: Path, state: dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_rejected_stat(
    candidate: MetadataCandidate,
    decision: dict[str, str],
    *,
    discarded_path: Path | None,
) -> dict[str, str]:
    return {
        "id": candidate.id,
        "title": str(candidate.metadata.get("title") or ""),
        "doi": str(candidate.metadata.get("doi") or ""),
        "reason": decision["reason"],
        "decision": decision["decision"],
        "discarded_path": str(discarded_path) if discarded_path is not None else "",
    }


def build_summary_payload(
    *,
    metadata_dir: Path,
    discarded_dir: Path,
    state_file: Path,
    summary_file: Path,
    total_candidates: int,
    remaining_candidates: int,
    apply_changes: bool,
    action: str,
    model: str,
    batch_size: int,
    preview_words: int,
    state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "metadata_dir": str(metadata_dir),
        "discarded_dir": str(discarded_dir),
        "state_file": str(state_file),
        "summary_file": str(summary_file),
        "model": model,
        "batch_size": batch_size,
        "abstract_preview_words": preview_words,
        "apply_changes": apply_changes,
        "action": action,
        "total_candidates": total_candidates,
        "remaining_candidates": remaining_candidates,
        "completed": bool(state.get("completed")),
        "reviewed_count": int(state.get("reviewed_count", 0)),
        "kept_count": int(state.get("kept_count", 0)),
        "dropped_count": int(state.get("dropped_count", 0)),
        "uncertain_count": int(state.get("uncertain_count", 0)),
        "invalid_count": int(state.get("invalid_count", 0)),
        "newly_rejected_count": len(state.get("newly_rejected", [])),
        "newly_rejected": list(state.get("newly_rejected", [])),
    }


def persist_summary(summary_file: Path, summary: dict[str, Any]) -> None:
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_refilter(
    *,
    metadata_dir: Path,
    discarded_dir: Path,
    model: str,
    batch_size: int,
    preview_words: int,
    limit: int | None,
    action: str,
    apply_changes: bool,
    state_file: Path,
    summary_file: Path,
    reset_state: bool,
) -> int:
    candidates = iter_metadata_candidates(metadata_dir, preview_words=preview_words)
    if limit is not None:
        candidates = candidates[:limit]

    if not candidates:
        print(f"[INFO] No valid metadata files found in {metadata_dir}")
        return 0

    state = load_state(state_file, reset_state=reset_state)
    processed_ids = set(state.get("processed_ids", []))
    remaining_candidates = [candidate for candidate in candidates if candidate.id not in processed_ids]

    print(f"[INFO] Total metadata candidates: {len(candidates)}")
    print(f"[INFO] Already reviewed from state: {len(processed_ids)}")
    print(f"[INFO] Remaining to review: {len(remaining_candidates)}")

    for batch in batched(remaining_candidates, batch_size):
        decisions_by_id = classify_metadata_candidates(
            batch,
            model=model,
        )

        for candidate in batch:
            decision = decisions_by_id.get(candidate.id)
            state["processed_ids"] = list(processed_ids)

            if not decision:
                state["invalid_count"] = int(state.get("invalid_count", 0)) + 1
                state["reviewed_count"] = int(state.get("reviewed_count", 0)) + 1
                processed_ids.add(candidate.id)
                state["processed_ids"] = sorted(processed_ids)
                persist_state(state_file, state)
                print(f"[SKIP INVALID] {candidate.path.name}: missing decision")
                continue

            if decision["decision"] == "keep":
                state["kept_count"] = int(state.get("kept_count", 0)) + 1
                state["reviewed_count"] = int(state.get("reviewed_count", 0)) + 1
                processed_ids.add(candidate.id)
                state["processed_ids"] = sorted(processed_ids)
                persist_state(state_file, state)
                print(f"[KEEP] {candidate.path.name}: {decision['reason']}")
                continue

            if decision["decision"] == "uncertain":
                state["uncertain_count"] = int(state.get("uncertain_count", 0)) + 1
                state["reviewed_count"] = int(state.get("reviewed_count", 0)) + 1
                processed_ids.add(candidate.id)
                state["processed_ids"] = sorted(processed_ids)
                persist_state(state_file, state)
                print(f"[UNCERTAIN] {candidate.path.name}: {decision['reason']}")
                continue

            discarded_path: Path | None = None
            if not apply_changes:
                print(f"[DRY-RUN DROP] {candidate.path.name}: {decision['reason']}")
            elif action == "delete":
                candidate.path.unlink(missing_ok=False)
                print(f"[DELETED] {candidate.path.name}: {decision['reason']}")
            else:
                discarded_dir.mkdir(parents=True, exist_ok=True)
                discarded_path = discarded_dir / f"{candidate.id}.json"
                discarded_path.write_text(
                    json.dumps(build_discarded_payload(candidate, decision), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                candidate.path.unlink(missing_ok=False)
                print(f"[DISCARDED] {candidate.path.name} -> {discarded_path.name}: {decision['reason']}")

            state["dropped_count"] = int(state.get("dropped_count", 0)) + 1
            state["reviewed_count"] = int(state.get("reviewed_count", 0)) + 1
            newly_rejected = list(state.get("newly_rejected", []))
            newly_rejected.append(build_rejected_stat(candidate, decision, discarded_path=discarded_path))
            state["newly_rejected"] = newly_rejected
            processed_ids.add(candidate.id)
            state["processed_ids"] = sorted(processed_ids)
            persist_state(state_file, state)

    state["completed"] = True
    persist_state(state_file, state)
    summary = build_summary_payload(
        metadata_dir=metadata_dir,
        discarded_dir=discarded_dir,
        state_file=state_file,
        summary_file=summary_file,
        total_candidates=len(candidates),
        remaining_candidates=max(0, len(candidates) - int(state.get("reviewed_count", 0))),
        apply_changes=apply_changes,
        action=action,
        model=model,
        batch_size=batch_size,
        preview_words=preview_words,
        state=state,
    )
    persist_summary(summary_file, summary)

    print("")
    print("Refilter summary")
    print(f"- Metadata scanned: {len(candidates)}")
    print(f"- Reviewed total:   {summary['reviewed_count']}")
    print(f"- Kept:             {summary['kept_count']}")
    print(f"- Dropped:          {summary['dropped_count']}")
    print(f"- Uncertain:        {summary['uncertain_count']}")
    print(f"- Invalid:          {summary['invalid_count']}")
    print(f"- Newly rejected:   {summary['newly_rejected_count']}")
    print(f"- Apply changes:    {'yes' if apply_changes else 'no'}")
    print(f"- Action:           {action}")
    print(f"- State file:       {ctx.display_path(state_file)}")
    print(f"- Summary file:     {ctx.display_path(summary_file)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Re-run paper_selector over canonical metadata files and remove LLM-dropped papers without touching the main pipeline."
    )
    parser.add_argument("--metadata-dir", type=Path, default=PATHS["metadata_dir"])
    parser.add_argument("--discarded-dir", type=Path, default=PATHS["discarded_dir"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--abstract-preview-words", type=int, default=DEFAULT_PREVIEW_WORDS)
    parser.add_argument("--limit", type=int, default=None, help="Procesa solo los primeros N metadata files")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--summary-file", type=Path, default=DEFAULT_SUMMARY_FILE)
    parser.add_argument(
        "--action",
        choices=("discard", "delete"),
        default="discard",
        help="discard: escribe un JSON en discarded_dir y borra el metadata original; delete: solo borra el metadata original",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica borrado real. Sin este flag solo muestra lo que se eliminaria.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Ignora el checkpoint previo y vuelve a revisar todo desde cero.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return run_refilter(
            metadata_dir=args.metadata_dir.expanduser().resolve(),
            discarded_dir=args.discarded_dir.expanduser().resolve(),
            model=str(args.model),
            batch_size=max(1, int(args.batch_size)),
            preview_words=max(1, int(args.abstract_preview_words)),
            limit=args.limit,
            action=str(args.action),
            apply_changes=bool(args.apply),
            state_file=args.state_file.expanduser().resolve(),
            summary_file=args.summary_file.expanduser().resolve(),
            reset_state=bool(args.reset_state),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
