"""T-801/T-602 — Montagem do `StateGraph` (fatia M1) + checkpointer.

Fluxo: N0 ingest → (erro? END : N1 index) → N2 classify → N3 select_weights → Trajetória →
N5 aggregate → N7 build_report → END. Aresta condicional de erro em N0 (CA-01). Compila com
checkpointer (MemorySaver dev) para suportar interrupt/resume futuro por `thread_id` (RF-24).

Fan-out das 7 dimensões, divergência/HITL, histórico e budget entram em M2..M5.

Rastreabilidade: plan §1.1/§5; RF-02; CA-01.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from avalia.graph.nodes import (
    TrajetoriaContributor,
    make_trajetoria_node,
    n0_ingest,
    n1_index,
    n2_classify,
    n3_select_weights,
    n5_aggregate,
    n7_build_report,
    route_after_ingest,
)
from avalia.graph.state import AvaliaState


def build_avalia_graph(
    *, contributor: TrajetoriaContributor | None = None, checkpointer: Any | None = None
) -> Any:
    """Constrói e compila o grafo de avaliação do M1."""
    # StateGraph é genérico e invariante no schema de estado; sob mypy strict o tipo do nó
    # (Callable[[AvaliaState], dict]) não encaixa no _Node[Never] esperado. Tratamos o builder
    # como Any — fronteira pragmática com o typing do LangGraph, sem afetar o runtime.
    g: Any = StateGraph(AvaliaState)
    g.add_node("ingest", n0_ingest)
    g.add_node("index", n1_index)
    g.add_node("classify", n2_classify)
    g.add_node("select_weights", n3_select_weights)
    g.add_node("trajetoria", make_trajetoria_node(contributor))
    g.add_node("aggregate", n5_aggregate)
    g.add_node("build_report", n7_build_report)

    g.set_entry_point("ingest")
    g.add_conditional_edges("ingest", route_after_ingest, {"error": END, "continue": "index"})
    g.add_edge("index", "classify")
    g.add_edge("classify", "select_weights")
    g.add_edge("select_weights", "trajetoria")
    g.add_edge("trajetoria", "aggregate")
    g.add_edge("aggregate", "build_report")
    g.add_edge("build_report", END)

    return g.compile(checkpointer=checkpointer or MemorySaver())
