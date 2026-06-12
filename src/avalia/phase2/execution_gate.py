"""T-804 — `execution_gate` da Fase 2 (RF-23). NO-OP ausente do grafo na Fase 1.

Posição reservada entre N5 e N7 onde a Fase 2 fará `interrupt()` de aprovação ANTES de qualquer
execução do alvo. Na Fase 1 é um no-op que NUNCA é adicionado ao grafo — reusa o padrão de
interrupt/resume do `human_gate` (RF-24), sem custo de construção agora. NÃO executa o alvo.
"""

from __future__ import annotations

from typing import Any


def execution_gate(state: Any) -> dict[str, Any]:  # pragma: no cover - gancho Fase 2, não usado
    """No-op da Fase 1. Na Fase 2, pediria aprovação humana explícita antes de executar (RF-23)."""
    raise NotImplementedError(
        "execution_gate é um gancho da Fase 2; a Fase 1 nunca executa o alvo."
    )
