"""T-803 — Streaming de progresso via `astream_events` (plan §3.12).

Projeta os eventos do grafo em `ProgressEvent`s simples para consumidores reativos (CLI/UI):
início/fim de nó, score parcial de cada dimensão ao concluir seu ramo do fan-out, e o flag de
parcialidade do `BudgetState`. É PROJEÇÃO pura do State — não altera contratos nem o caminho do
laudo, e é não-bloqueante (sustenta US-02/06/09).

Nada executa o alvo (RNF-05): apenas observa eventos do grafo de avaliação.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from avalia.domain.enums import Dimension

# Nós cujo progresso é exposto ao consumidor.
_TRACKED: frozenset[str] = frozenset(
    {
        "ingest",
        "index",
        "classify",
        "select_weights",
        "detect_divergence",
        "human_gate",
        "budget_degraded",
        "aggregate",
        "compare_history",
        "build_report",
        *(f"dim_{d.value}" for d in Dimension),
    }
)


class ProgressEvent(BaseModel):
    """Projeção de um evento de progresso do grafo (não é contrato do laudo)."""

    model_config = ConfigDict(frozen=True)

    kind: str  # node_start | node_end
    node: str
    dimension: str | None = None
    score: int | None = None
    partial: bool = False


def _project_end(node: str, output: Any) -> ProgressEvent:
    dimension: str | None = None
    score: int | None = None
    partial = False
    if isinstance(output, Mapping):
        results = output.get("dimension_results")
        if results:
            dr = results[0]
            dimension = getattr(getattr(dr, "dimension", None), "value", None)
            score = getattr(dr, "score", None)
        budget = output.get("budget")
        partial = bool(getattr(budget, "partial", False))
    return ProgressEvent(
        kind="node_end", node=node, dimension=dimension, score=score, partial=partial
    )


async def stream_progress(
    graph: Any, inputs: Mapping[str, Any], config: Mapping[str, Any]
) -> AsyncIterator[ProgressEvent]:
    """Itera os eventos do grafo e emite `ProgressEvent`s por nó rastreado."""
    async for ev in graph.astream_events(inputs, config=config, version="v2"):
        name = ev.get("name", "")
        if name not in _TRACKED:
            continue
        etype = ev.get("event")
        if etype == "on_chain_start":
            yield ProgressEvent(kind="node_start", node=name)
        elif etype == "on_chain_end":
            data = ev.get("data") or {}
            yield _project_end(name, data.get("output"))
