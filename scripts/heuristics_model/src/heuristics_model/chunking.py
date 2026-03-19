from __future__ import annotations

from .models import DocumentStructure, TextNode


def _span_from_nodes(nodes: list[TextNode]) -> str:
    if not nodes:
        return ""
    start = min(node.source_span.start_line for node in nodes)
    end = max(node.source_span.end_line for node in nodes)
    return f"{start}:{end}"


def build_chunks(structure: DocumentStructure) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for section in structure.sections:
        if section.content:
            chunks.append(
                {
                    "section": section.title,
                    "subsection": "",
                    "text": "\n".join(node.text for node in section.content).strip(),
                    "source_span": _span_from_nodes(section.content),
                }
            )
        for subsection in section.subsections:
            if not subsection.content:
                continue
            chunks.append(
                {
                    "section": section.title,
                    "subsection": subsection.title,
                    "text": "\n".join(node.text for node in subsection.content).strip(),
                    "source_span": _span_from_nodes(subsection.content),
                }
            )
    return [chunk for chunk in chunks if chunk["text"]]
