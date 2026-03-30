from __future__ import annotations

from ..tools.citation_exploration import run_interactive_exploration, run_nutrition_rag_exploration


def run_metadata_exploration_flow(mode: str = "interactive") -> None:
    if mode == "interactive":
        run_interactive_exploration()
        return
    if mode == "nutrition-rag":
        run_nutrition_rag_exploration()
        return
    raise ValueError(f"Modo metadata no soportado: {mode}")
