from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["section", "subsection", "text"]


@dataclass(slots=True)
class SourceSpan:
    start_line: int
    end_line: int


@dataclass(slots=True)
class Block:
    level: int
    raw_heading: str | None
    normalized_heading: str | None
    text: str
    source_span: SourceSpan


@dataclass(slots=True)
class ClassifiedHeading:
    role: Role
    canonical_label: str | None
    applied_rules: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TextNode:
    text: str
    source_span: SourceSpan


@dataclass(slots=True)
class IgnoredTable:
    text: str
    source_span: SourceSpan


@dataclass(slots=True)
class SubsectionNode:
    title: str
    content: list[TextNode] = field(default_factory=list)


@dataclass(slots=True)
class SectionNode:
    title: str
    subsections: list[SubsectionNode] = field(default_factory=list)
    content: list[TextNode] = field(default_factory=list)


@dataclass(slots=True)
class DocumentStructure:
    sections: list[SectionNode] = field(default_factory=list)
    ignored_tables: list[IgnoredTable] = field(default_factory=list)
