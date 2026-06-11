"""T-801/T-602/T-311 — Montagem do `StateGraph` + checkpointer.

Fluxo: N0 ingest → (erro? END : N1 index) → N2 classify → N3 select_weights → **fan-out das 7
dimensões** → fan-in em N5 aggregate → N7 build_report → END. Aresta condicional de erro em N0
(CA-01). Compila com checkpointer (MemorySaver dev) para interrupt/resume futuro (RF-24).

O fan-in é implícito: `aggregate` só roda quando os 7 ramos concluem (reducer `operator.add` em
`dimension_results`; ordenação estável por `Dimension` é feita na agregação — T-311).

Divergência/HITL (M3), histórico (M4) e budget (M5) entram depois.

Rastreabilidade: plan §1.1/§5; RF-02, RF-09; CA-01; T-311.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from avalia.domain.enums import Dimension
from avalia.graph.nodes import (
    make_build_report_node,
    make_compare_history_node,
    make_detect_divergence_node,
    make_dimension_node,
    n0_ingest,
    n1_index,
    n2_classify,
    n3_select_weights,
    n4h_human_gate,
    n5_aggregate,
    route_after_divergence,
    route_after_ingest,
)
from avalia.graph.state import AvaliaState
from avalia.judge.framework import GatewayLike
from avalia.persistence.repository import ReportRepository


def build_avalia_graph(
    *,
    gateway: GatewayLike | None = None,
    repository: ReportRepository | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Constrói e compila o grafo de avaliação (7 dimensões em fan-out)."""
    # StateGraph é genérico e invariante no schema de estado; sob mypy strict o tipo do nó
    # (Callable[[AvaliaState], dict]) não encaixa no _Node[Never] esperado. Tratamos o builder
    # como Any — fronteira pragmática com o typing do LangGraph, sem afetar o runtime.
    g: Any = StateGraph(AvaliaState)
    g.add_node("ingest", n0_ingest)
    g.add_node("index", n1_index)
    g.add_node("classify", n2_classify)
    g.add_node("select_weights", n3_select_weights)
    g.add_node("detect_divergence", make_detect_divergence_node(gateway))
    g.add_node("human_gate", n4h_human_gate)
    g.add_node("aggregate", n5_aggregate)
    g.add_node("compare_history", make_compare_history_node(repository))
    g.add_node("build_report", make_build_report_node(repository))

    dim_nodes = [f"dim_{d.value}" for d in Dimension]
    for d, name in zip(Dimension, dim_nodes, strict=True):
        g.add_node(name, make_dimension_node(d, gateway))

    g.set_entry_point("ingest")
    g.add_conditional_edges("ingest", route_after_ingest, {"error": END, "continue": "index"})
    g.add_edge("index", "classify")
    g.add_edge("classify", "select_weights")
    for name in dim_nodes:  # fan-out
        g.add_edge("select_weights", name)
        g.add_edge(name, "detect_divergence")  # fan-in (N4 espera os 7)
    # N4 → human_gate (divergência persistente) vs. aggregate
    g.add_conditional_edges(
        "detect_divergence",
        route_after_divergence,
        {"human": "human_gate", "aggregate": "aggregate"},
    )
    g.add_edge("human_gate", "aggregate")
    g.add_edge("aggregate", "compare_history")  # N6: comparação histórica (CB-06 se sem anterior)
    g.add_edge("compare_history", "build_report")
    g.add_edge("build_report", END)

    return g.compile(checkpointer=checkpointer or MemorySaver())
