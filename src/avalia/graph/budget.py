"""T-802 — Guarda transversal de budget (RF-12, RNF-12).

`over_budget` compara o `BudgetState` acumulado contra os tetos de custo/tempo da config. É
consultado no roteamento (build_graph): ao estourar o teto, o grafo desvia da cara fan-out de
juízes para um caminho degradado (determinístico) e emite **laudo parcial honesto** (CA-13).
Reaproveitado por CB-10 (fallback de modelo esgotado também leva a parcial).

Nada executa o alvo (RNF-05): só lê estado e config.
"""

from __future__ import annotations

import time

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.graph.state import AvaliaState


def over_budget(state: AvaliaState, config: EvaluatorConfig) -> str | None:
    """Razão de estouro de teto (custo ou tempo), ou None se dentro do orçamento."""
    budget = state.get("budget")
    if budget is None:
        return None
    if config.cost_ceiling is not None and budget.accumulated_cost >= config.cost_ceiling:
        return f"custo acumulado {budget.accumulated_cost:.4f} ≥ teto {config.cost_ceiling}"
    if config.time_ceiling_s is not None:
        elapsed = time.monotonic() - budget.started_monotonic
        if elapsed >= config.time_ceiling_s:
            return f"tempo decorrido {elapsed:.2f}s ≥ teto {config.time_ceiling_s}s"
    return None
