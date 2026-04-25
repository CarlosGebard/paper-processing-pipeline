from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml

from src import config as ctx


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "via",
    "with",
}
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    year: int | None = None
    doi: str | None = None
    journal: str | None = None
    citation_count: int | None = None


@dataclass(frozen=True)
class ProcessedPaper:
    record: PaperRecord
    normalized_title: str
    tokens: tuple[str, ...]
    term_counts: Counter[str]


@dataclass(frozen=True)
class TopicKeyword:
    raw: str
    normalized: str


@dataclass(frozen=True)
class TopicDefinition:
    name: str
    keywords: tuple[TopicKeyword, ...]


@dataclass(frozen=True)
class TopicMatch:
    topic: str
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    processed_papers: tuple[ProcessedPaper, ...]
    topic_matches: dict[str, tuple[TopicMatch, ...]]
    term_doc_freq: Counter[str]
    term_total_freq: Counter[str]
    inverted_index: dict[str, tuple[str, ...]]
    mapped_terms: set[str]


@dataclass(frozen=True)
class CandidateTermStats:
    term: str
    n_tokens: int
    doc_freq: int
    total_freq: int
    citation_weight: float
    combined_score: float
    example_titles: tuple[str, ...]


@dataclass(frozen=True)
class DraftTopicGroup:
    topic_name: str
    keywords: tuple[str, ...]
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class BootstrapTopicRule:
    topic_name: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class BootstrapTopicConfig:
    excluded_terms: tuple[str, ...]
    topic_rules: tuple[BootstrapTopicRule, ...]


def normalize_text(value: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return " ".join(TOKEN_PATTERN.findall(ascii_text))


def tokenize_title(title: str) -> list[str]:
    normalized = normalize_text(title)
    return [token for token in normalized.split() if token and token not in STOPWORDS]


def extract_ngrams(tokens: list[str], min_n: int = 1, max_n: int = 3) -> list[str]:
    ngrams: list[str] = []
    for size in range(min_n, max_n + 1):
        if len(tokens) < size:
            continue
        for index in range(0, len(tokens) - size + 1):
            ngrams.append(" ".join(tokens[index : index + size]))
    return ngrams


def load_papers(input_path: Path) -> list[PaperRecord]:
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        rows = _load_csv_rows(input_path)
    elif suffix in {".jsonl", ".ndjson"}:
        rows = _load_jsonl_rows(input_path)
    else:
        raise ValueError(
            f"Formato no soportado para {input_path.name}. Usa CSV o JSONL."
        )

    papers: list[PaperRecord] = []
    for index, row in enumerate(rows, start=1):
        paper_id = str(row.get("paper_id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not paper_id:
            raise ValueError(f"Fila {index}: falta paper_id.")
        if not title:
            raise ValueError(f"Fila {index}: falta title.")
        papers.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                year=_parse_optional_year(row.get("year"), index=index),
                doi=_normalize_optional_field(row.get("doi")),
                journal=_normalize_optional_field(row.get("journal")),
                citation_count=_parse_optional_year(row.get("citation_count"), index=index)
                if row.get("citation_count") not in (None, "")
                else None,
            )
        )
    return papers


def _load_csv_rows(input_path: Path) -> list[dict[str, Any]]:
    with input_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_jsonl_rows(input_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Linea {line_number}: cada entrada JSONL debe ser un objeto.")
        rows.append(payload)
    return rows


def _parse_optional_year(value: Any, *, index: int) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"Fila {index}: year invalido: {value!r}") from exc


def _normalize_optional_field(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def load_metadata_citations_as_papers(input_path: Path) -> list[PaperRecord]:
    rows = _load_csv_rows(input_path)
    papers: list[PaperRecord] = []
    for index, row in enumerate(rows, start=1):
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        citation_count = row.get("citation_count")
        year_value = row.get("year")
        papers.append(
            PaperRecord(
                paper_id=f"citation-row-{index}",
                title=title,
                year=_parse_optional_year(year_value, index=index) if year_value not in (None, "") else None,
                doi=_normalize_optional_field(row.get("doi")),
                journal=_normalize_optional_field(row.get("journal")),
                citation_count=_parse_optional_year(citation_count, index=index)
                if citation_count not in (None, "")
                else None,
            )
        )
    return papers


def load_topics_dictionary(topics_path: Path) -> list[TopicDefinition]:
    raw = _load_yaml_or_json(topics_path)
    if not isinstance(raw, dict):
        raise ValueError("El archivo de topics debe ser un objeto YAML/JSON.")
    topics_payload = raw.get("topics")
    if not isinstance(topics_payload, dict) or not topics_payload:
        raise ValueError("El archivo de topics debe incluir un bloque 'topics' no vacio.")

    topics: list[TopicDefinition] = []
    for topic_name, topic_config in topics_payload.items():
        if not isinstance(topic_name, str) or not topic_name.strip():
            raise ValueError("Cada topic debe tener un nombre string no vacio.")
        if not isinstance(topic_config, dict):
            raise ValueError(f"El topic {topic_name!r} debe ser un objeto.")
        keywords_payload = topic_config.get("keywords")
        if not isinstance(keywords_payload, list) or not keywords_payload:
            raise ValueError(f"El topic {topic_name!r} debe tener una lista 'keywords' no vacia.")
        normalized_keywords: list[TopicKeyword] = []
        for keyword in keywords_payload:
            if not isinstance(keyword, str) or not keyword.strip():
                raise ValueError(f"El topic {topic_name!r} contiene un keyword invalido.")
            normalized = normalize_keyword(keyword)
            if not normalized:
                raise ValueError(
                    f"El topic {topic_name!r} contiene un keyword vacio tras normalizacion: {keyword!r}."
                )
            normalized_keywords.append(TopicKeyword(raw=keyword.strip(), normalized=normalized))
        topics.append(
            TopicDefinition(
                name=topic_name.strip(),
                keywords=tuple(_dedupe_topic_keywords(normalized_keywords)),
            )
        )
    return topics


def _load_yaml_or_json(input_path: Path) -> Any:
    suffix = input_path.suffix.lower()
    text = input_path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _dedupe_topic_keywords(keywords: list[TopicKeyword]) -> list[TopicKeyword]:
    seen: set[str] = set()
    deduped: list[TopicKeyword] = []
    for keyword in keywords:
        if keyword.normalized in seen:
            continue
        seen.add(keyword.normalized)
        deduped.append(keyword)
    return deduped


def normalize_keyword(keyword: str) -> str:
    return " ".join(tokenize_title(keyword))


def load_bootstrap_topic_config(
    config_path: Path | None = None,
) -> BootstrapTopicConfig:
    if config_path is not None:
        input_path = config_path
    else:
        from analytics import paths as analytics_ctx

        input_path = (
            analytics_ctx.PRE_INGESTION_BOOTSTRAP_RULES_YAML
            if analytics_ctx.PRE_INGESTION_BOOTSTRAP_RULES_YAML.exists()
            else ctx.PRE_INGESTION_BOOTSTRAP_RULES_YAML
        )
    raw = _load_yaml_or_json(input_path)
    if not isinstance(raw, dict):
        raise ValueError("El archivo bootstrap topics debe ser un objeto YAML/JSON.")

    excluded_payload = raw.get("excluded_terms") or []
    if not isinstance(excluded_payload, list):
        raise ValueError("El archivo bootstrap topics debe incluir 'excluded_terms' como lista.")
    excluded_terms = tuple(
        normalize_text(term)
        for term in excluded_payload
        if isinstance(term, str) and normalize_text(term)
    )

    rules_payload = raw.get("topic_rules")
    if not isinstance(rules_payload, dict) or not rules_payload:
        raise ValueError("El archivo bootstrap topics debe incluir un bloque 'topic_rules' no vacio.")

    topic_rules: list[BootstrapTopicRule] = []
    for topic_name, topic_config in rules_payload.items():
        if not isinstance(topic_name, str) or not topic_name.strip():
            raise ValueError("Cada topic rule debe tener un nombre string no vacio.")
        if not isinstance(topic_config, dict):
            raise ValueError(f"La topic rule {topic_name!r} debe ser un objeto.")
        patterns_payload = topic_config.get("patterns")
        if not isinstance(patterns_payload, list) or not patterns_payload:
            raise ValueError(f"La topic rule {topic_name!r} debe tener una lista 'patterns' no vacia.")
        normalized_patterns = tuple(
            normalize_text(pattern)
            for pattern in patterns_payload
            if isinstance(pattern, str) and normalize_text(pattern)
        )
        if not normalized_patterns:
            raise ValueError(f"La topic rule {topic_name!r} no tiene patterns validos.")
        topic_rules.append(
            BootstrapTopicRule(
                topic_name=topic_name.strip(),
                patterns=normalized_patterns,
            )
        )

    return BootstrapTopicConfig(
        excluded_terms=tuple(dict.fromkeys(excluded_terms)),
        topic_rules=tuple(topic_rules),
    )


def filter_papers_by_year(
    papers: list[PaperRecord],
    *,
    min_year: int | None = None,
    max_year: int | None = None,
) -> list[PaperRecord]:
    filtered: list[PaperRecord] = []
    for paper in papers:
        if paper.year is None and (min_year is not None or max_year is not None):
            continue
        if min_year is not None and paper.year is not None and paper.year < min_year:
            continue
        if max_year is not None and paper.year is not None and paper.year > max_year:
            continue
        filtered.append(paper)
    return filtered


def process_papers(papers: list[PaperRecord]) -> list[ProcessedPaper]:
    processed: list[ProcessedPaper] = []
    for paper in papers:
        tokens = tokenize_title(paper.title)
        term_counts = Counter(extract_ngrams(tokens))
        processed.append(
            ProcessedPaper(
                record=paper,
                normalized_title=" ".join(tokens),
                tokens=tuple(tokens),
                term_counts=term_counts,
            )
        )
    return processed


def audit_topics(
    papers: list[PaperRecord],
    topics: list[TopicDefinition],
) -> AuditResult:
    processed_papers = process_papers(papers)
    term_total_freq: Counter[str] = Counter()
    term_doc_freq: Counter[str] = Counter()
    inverted_index_accumulator: dict[str, list[str]] = defaultdict(list)
    topic_matches: dict[str, tuple[TopicMatch, ...]] = {}
    mapped_terms: set[str] = set()

    for topic in topics:
        mapped_terms.update(keyword.normalized for keyword in topic.keywords)

    for processed in processed_papers:
        term_total_freq.update(processed.term_counts)
        for term in processed.term_counts:
            term_doc_freq[term] += 1
            inverted_index_accumulator[term].append(processed.record.paper_id)
        topic_matches[processed.record.paper_id] = tuple(match_topics_for_paper(processed, topics))

    inverted_index = {
        term: tuple(sorted(paper_ids))
        for term, paper_ids in sorted(inverted_index_accumulator.items())
    }

    return AuditResult(
        processed_papers=tuple(processed_papers),
        topic_matches=topic_matches,
        term_doc_freq=term_doc_freq,
        term_total_freq=term_total_freq,
        inverted_index=inverted_index,
        mapped_terms=mapped_terms,
    )


def match_topics_for_paper(
    processed: ProcessedPaper,
    topics: list[TopicDefinition],
) -> list[TopicMatch]:
    matches: list[TopicMatch] = []
    available_terms = set(processed.term_counts)
    for topic in topics:
        matched_terms = sorted(
            keyword.raw
            for keyword in topic.keywords
            if keyword.normalized in available_terms
        )
        if matched_terms:
            matches.append(TopicMatch(topic=topic.name, matched_terms=tuple(matched_terms)))
    return matches


def build_paper_topic_rows(audit: AuditResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for processed in audit.processed_papers:
        matches = audit.topic_matches.get(processed.record.paper_id, ())
        rows.append(
            {
                "paper_id": processed.record.paper_id,
                "title": processed.record.title,
                "matched_topics": "; ".join(match.topic for match in matches),
                "matched_terms": "; ".join(
                    f"{match.topic}:{', '.join(match.matched_terms)}" for match in matches
                ),
            }
        )
    return rows


def build_topic_stats_rows(audit: AuditResult) -> list[dict[str, str | int | float]]:
    total_papers = len(audit.processed_papers)
    topic_counts: Counter[str] = Counter()
    for matches in audit.topic_matches.values():
        for match in matches:
            topic_counts[match.topic] += 1

    rows = [
        {
            "topic": topic,
            "paper_count": count,
            "relative_frequency": round((count / total_papers) if total_papers else 0.0, 6),
        }
        for topic, count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return rows


def build_term_stats_rows(audit: AuditResult) -> list[dict[str, str | int]]:
    return [
        {
            "term": term,
            "doc_freq": audit.term_doc_freq[term],
            "total_freq": audit.term_total_freq[term],
        }
        for term in sorted(
            audit.term_doc_freq,
            key=lambda value: (-audit.term_doc_freq[value], -audit.term_total_freq[value], value),
        )
    ]


def build_topic_cooccurrence_rows(audit: AuditResult) -> list[dict[str, str | int]]:
    cooccurrence: Counter[tuple[str, str]] = Counter()
    for matches in audit.topic_matches.values():
        topics = sorted(match.topic for match in matches)
        for topic_a, topic_b in combinations(topics, 2):
            cooccurrence[(topic_a, topic_b)] += 1
    return [
        {"topic_a": topic_a, "topic_b": topic_b, "count": count}
        for (topic_a, topic_b), count in sorted(
            cooccurrence.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
    ]


def build_unclassified_rows(audit: AuditResult) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for processed in audit.processed_papers:
        if audit.topic_matches.get(processed.record.paper_id):
            continue
        rows.append(
            {
                "paper_id": processed.record.paper_id,
                "title": processed.record.title,
                "year": processed.record.year or "",
                "doi": processed.record.doi or "",
                "journal": processed.record.journal or "",
            }
        )
    return rows


def build_unmapped_term_rows(
    audit: AuditResult,
    *,
    min_doc_freq: int = 2,
    top_n: int | None = None,
) -> list[dict[str, str | int]]:
    rows = [
        {
            "term": term,
            "doc_freq": audit.term_doc_freq[term],
            "total_freq": audit.term_total_freq[term],
        }
        for term in sorted(
            audit.term_doc_freq,
            key=lambda value: (-audit.term_doc_freq[value], -audit.term_total_freq[value], value),
        )
        if audit.term_doc_freq[term] >= min_doc_freq and term not in audit.mapped_terms
    ]
    if top_n is not None:
        return rows[:top_n]
    return rows


def build_summary(
    audit: AuditResult,
    *,
    top_n_terms: int = 10,
    top_n_topics: int = 10,
    unmapped_min_doc_freq: int = 2,
    top_n_unmapped_terms: int | None = None,
) -> dict[str, Any]:
    topic_rows = build_topic_stats_rows(audit)
    term_rows = build_term_stats_rows(audit)
    unclassified_rows = build_unclassified_rows(audit)
    unmapped_rows = build_unmapped_term_rows(
        audit,
        min_doc_freq=unmapped_min_doc_freq,
        top_n=top_n_unmapped_terms if top_n_unmapped_terms is not None else top_n_terms,
    )
    return {
        "paper_count": len(audit.processed_papers),
        "classified_paper_count": len(audit.processed_papers) - len(unclassified_rows),
        "unclassified_paper_count": len(unclassified_rows),
        "top_topics": topic_rows[:top_n_topics],
        "top_terms": term_rows[:top_n_terms],
        "top_unmapped_terms": unmapped_rows,
    }


def bootstrap_candidate_terms_from_citations(
    papers: list[PaperRecord],
    *,
    min_n: int = 2,
    max_n: int = 3,
    min_doc_freq: int = 2,
    top_n: int | None = None,
    excluded_terms: set[str] | None = None,
    max_examples_per_term: int = 3,
    bootstrap_config_path: Path | None = None,
) -> list[CandidateTermStats]:
    bootstrap_config = load_bootstrap_topic_config(bootstrap_config_path)
    excluded = set(bootstrap_config.excluded_terms)
    if excluded_terms:
        excluded.update(normalize_text(term) for term in excluded_terms if term.strip())

    doc_freq: Counter[str] = Counter()
    total_freq: Counter[str] = Counter()
    citation_weight: defaultdict[str, float] = defaultdict(float)
    example_titles: defaultdict[str, list[str]] = defaultdict(list)

    for paper in papers:
        tokens = tokenize_title(paper.title)
        terms = extract_ngrams(tokens, min_n=min_n, max_n=max_n)
        term_counter = Counter(terms)
        citations = _paper_citation_weight(paper)
        for term, freq in term_counter.items():
            if _should_exclude_bootstrap_term(term, excluded):
                continue
            total_freq[term] += freq
            doc_freq[term] += 1
            citation_weight[term] += citations
            if len(example_titles[term]) < max_examples_per_term:
                example_titles[term].append(paper.title)

    rows = [
        CandidateTermStats(
            term=term,
            n_tokens=len(term.split()),
            doc_freq=doc_freq[term],
            total_freq=total_freq[term],
            citation_weight=round(citation_weight[term], 4),
            combined_score=round(_combined_bootstrap_score(doc_freq[term], total_freq[term], citation_weight[term]), 4),
            example_titles=tuple(example_titles[term]),
        )
        for term in doc_freq
        if doc_freq[term] >= min_doc_freq
    ]
    rows.sort(key=lambda row: (-row.combined_score, -row.doc_freq, -row.citation_weight, row.term))
    return rows[:top_n] if top_n is not None else rows


def _paper_citation_weight(paper: PaperRecord) -> float:
    if paper.citation_count is None:
        return 0.0
    citation_count = max(paper.citation_count, 0)
    return math.log1p(citation_count)


def _should_exclude_bootstrap_term(term: str, excluded: set[str]) -> bool:
    if term in excluded:
        return True
    tokens = term.split()
    if not tokens:
        return True
    if any(token.isdigit() and len(token) == 4 for token in tokens):
        return True
    if tokens[0].isdigit() or tokens[-1].isdigit():
        return True
    if len(tokens) >= 2 and all(token in {"global", "worldwide", "national", "international", "european", "american"} for token in tokens):
        return True
    return False


def _combined_bootstrap_score(doc_freq_value: int, total_freq_value: int, citation_weight_value: float) -> float:
    return (doc_freq_value * 3.0) + total_freq_value + (citation_weight_value * 0.75)


def candidate_term_rows_to_csv(rows: list[CandidateTermStats]) -> list[dict[str, str | int | float]]:
    return [
        {
            "term": row.term,
            "n_tokens": row.n_tokens,
            "doc_freq": row.doc_freq,
            "total_freq": row.total_freq,
            "citation_weight": row.citation_weight,
            "combined_score": row.combined_score,
            "example_titles": " | ".join(row.example_titles),
        }
        for row in rows
    ]


def build_draft_topics_yaml_payload(
    candidate_rows: list[CandidateTermStats],
    *,
    min_keywords_per_topic: int = 2,
    max_keywords_per_topic: int = 10,
    bootstrap_config_path: Path | None = None,
) -> dict[str, Any]:
    bootstrap_config = load_bootstrap_topic_config(bootstrap_config_path)
    remaining_terms = {row.term for row in candidate_rows}
    groups: list[DraftTopicGroup] = []

    for rule in bootstrap_config.topic_rules:
        matched = sorted(
            term
            for term in remaining_terms
            if any(pattern in term for pattern in rule.patterns)
        )
        if len(matched) < min_keywords_per_topic:
            continue
        keywords = tuple(matched[:max_keywords_per_topic])
        groups.append(
            DraftTopicGroup(
                topic_name=rule.topic_name,
                keywords=keywords,
                matched_terms=tuple(matched),
            )
        )
        for term in matched:
            remaining_terms.discard(term)

    topics = {
        group.topic_name: {
            "keywords": list(group.keywords),
        }
        for group in groups
    }
    return {
        "topics": topics,
        "review_candidates": {
            "unmatched_terms": sorted(remaining_terms),
        },
    }


def write_yaml(payload: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def write_csv_rows(rows: list[dict[str, Any]], output_path: Path, fieldnames: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(payload: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def export_audit_artifacts(
    audit: AuditResult,
    output_dir: Path,
    *,
    unmapped_min_doc_freq: int = 2,
    top_n_unmapped_terms: int | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paper_topics_rows = build_paper_topic_rows(audit)
    topic_stats_rows = build_topic_stats_rows(audit)
    term_stats_rows = build_term_stats_rows(audit)
    topic_cooccurrence_rows = build_topic_cooccurrence_rows(audit)
    unclassified_rows = build_unclassified_rows(audit)
    unmapped_rows = build_unmapped_term_rows(
        audit,
        min_doc_freq=unmapped_min_doc_freq,
        top_n=top_n_unmapped_terms,
    )

    outputs = {
        "paper_topics": output_dir / "paper_topics.csv",
        "topic_stats": output_dir / "topic_stats.csv",
        "term_stats": output_dir / "term_stats.csv",
        "topic_cooccurrence": output_dir / "topic_cooccurrence.csv",
        "unclassified_papers": output_dir / "unclassified_papers.csv",
        "unmapped_frequent_terms": output_dir / "unmapped_frequent_terms.csv",
        "term_index": output_dir / "term_index.json",
        "summary": output_dir / "summary.json",
    }

    write_csv_rows(
        paper_topics_rows,
        outputs["paper_topics"],
        ["paper_id", "title", "matched_topics", "matched_terms"],
    )
    write_csv_rows(
        topic_stats_rows,
        outputs["topic_stats"],
        ["topic", "paper_count", "relative_frequency"],
    )
    write_csv_rows(
        term_stats_rows,
        outputs["term_stats"],
        ["term", "doc_freq", "total_freq"],
    )
    write_csv_rows(
        topic_cooccurrence_rows,
        outputs["topic_cooccurrence"],
        ["topic_a", "topic_b", "count"],
    )
    write_csv_rows(
        unclassified_rows,
        outputs["unclassified_papers"],
        ["paper_id", "title", "year", "doi", "journal"],
    )
    write_csv_rows(
        unmapped_rows,
        outputs["unmapped_frequent_terms"],
        ["term", "doc_freq", "total_freq"],
    )
    write_json(audit.inverted_index, outputs["term_index"])
    write_json(
        build_summary(
            audit,
            unmapped_min_doc_freq=unmapped_min_doc_freq,
            top_n_unmapped_terms=top_n_unmapped_terms,
        ),
        outputs["summary"],
    )
    return outputs
