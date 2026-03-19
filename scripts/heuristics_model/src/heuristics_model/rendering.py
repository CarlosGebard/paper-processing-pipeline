from __future__ import annotations

from .models import DocumentStructure


def _display_heading(text: str) -> str:
    return text.replace("_", " ").title()


def render_markdown(structure: DocumentStructure) -> str:
    lines: list[str] = []

    for section in structure.sections:
        lines.append(f"# {_display_heading(section.title)}")
        lines.append("")

        for node in section.content:
            lines.append(node.text)
            lines.append("")

        for subsection in section.subsections:
            lines.append(f"## {_display_heading(subsection.title)}")
            lines.append("")
            for node in subsection.content:
                lines.append(node.text)
                lines.append("")

    return "\n".join(lines).strip() + "\n"
