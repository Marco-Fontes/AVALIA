"""Human-in-the-loop (HITL) — escalonamento de divergência irresolúvel (RF-24, RNF-11).

Único gatilho de HITL na Fase 1 (plan §3.9). CLI primeiro, atrás de `ApprovalProvider`
(resolução #5); API/UI ficam como extensão. Nada aqui executa o alvo (RNF-05).
"""

from __future__ import annotations

from avalia.hitl.approval import (
    ApprovalProvider,
    CLIApprovalProvider,
    StaticApprovalProvider,
)
from avalia.hitl.runner import run_evaluation

__all__ = [
    "ApprovalProvider",
    "CLIApprovalProvider",
    "StaticApprovalProvider",
    "run_evaluation",
]
