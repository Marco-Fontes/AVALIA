"""T-804 — Porta `TargetRunner` da Fase 2 (D-01). VAZIA na Fase 1.

Contrato declarado para que a Fase 2 possa plugar um runner sandboxed do alvo, sem que a Fase 1
o referencie ou implemente. A Fase 1 NUNCA executa o alvo (RNF-05/S-04) — esta interface não é
chamada em nenhum caminho do grafo atual.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TargetRunner(Protocol):
    """Runner isolado do alvo (Fase 2). Não há implementação na Fase 1."""

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Executaria o alvo em ambiente isolado — apenas Fase 2, sob aprovação humana (RF-23)."""
        ...
