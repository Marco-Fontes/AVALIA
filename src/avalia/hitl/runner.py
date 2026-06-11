"""T-404 — Runner que dirige interrupt/resume do `human_gate`.

Invoca o grafo; enquanto houver `interrupt()` pendente, coleta uma `HumanDecision` por candidato
via o `ApprovalProvider` e retoma com `Command(resume=...)`. O checkpointer (MemorySaver) preserva
o estado entre a pausa e a retomada por `thread_id`.

Rastreabilidade: RF-24, RNF-05; CA-11; plan §3.8a/§3.9.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import Command

from avalia.domain.contracts import DivergenceCandidate
from avalia.hitl.approval import ApprovalProvider


def run_evaluation(
    graph: Any,
    inputs: dict[str, Any],
    *,
    approval_provider: ApprovalProvider,
    thread_id: str = "avalia",
) -> dict[str, Any]:
    """Executa a avaliação ponta-a-ponta, resolvendo pausas de HITL via o provider."""
    config = {"configurable": {"thread_id": thread_id}}
    result: dict[str, Any] = graph.invoke(inputs, config=config)

    while result.get("__interrupt__"):
        payload = result["__interrupt__"][0].value
        pending = [DivergenceCandidate.model_validate(c) for c in payload["pending"]]
        decisions = [approval_provider.decide(c).model_dump() for c in pending]
        result = graph.invoke(Command(resume=decisions), config=config)

    return result
