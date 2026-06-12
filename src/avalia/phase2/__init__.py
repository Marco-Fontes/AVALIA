"""T-804 — Ganchos de extensão da Fase 2 (S-05, D-01, O7–O9).

Pacote de **interfaces vazias**, projetadas para NÃO bloquear a Fase 2 sem custo de construção
agora. NADA aqui é referenciado pelo grafo da Fase 1, e NADA executa o alvo (RNF-05/S-04):
- `TargetRunner` (porta do runner sandboxed da Fase 2 — D-01).
- `execution_gate` (no-op ausente do grafo; padrão de `interrupt()` reaproveitável — RF-23).
- `TestCaseGenerator` (consumirá o TSM já existente para gerar casos — O8).

O slot `DimensionResult.dynamic_metrics` permanece OPACO (None na Fase 1); a Fase 2 refina o
tipo sem migrar o contrato de M0.
"""

from __future__ import annotations

from avalia.phase2.execution_gate import execution_gate
from avalia.phase2.runner import TargetRunner
from avalia.phase2.testgen import TestCaseGenerator

__all__ = ["TargetRunner", "TestCaseGenerator", "execution_gate"]
