"""Estado do grafo `AvaliaState` (plan §3.3). TypedDict com reducer no fan-out.

`dimension_results` usa `operator.add` para o fan-out paralelo das dimensões (M2) escrever sem
corrida; no M1 só a Trajetória escreve. Demais campos são `replace`.

Rastreabilidade: plan §3.3; RF-01, RF-04..08, RF-09..14, RF-15..22.
"""

from __future__ import annotations

import operator
import time
from typing import Annotated, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from avalia.domain.contracts import (
    AggregateScore,
    ComponentInventory,
    DimensionResult,
    DivergenceCandidate,
    DivergenceRecord,
    EvaluationReport,
    HumanDecision,
    TargetClassification,
    VersionComparison,
)
from avalia.domain.enums import Dimension, RunStatus
from avalia.domain.submission import Submission
from avalia.domain.tsm import TargetStaticModel
from avalia.domain.weights import WeightProfile


class BudgetState(BaseModel):
    """Estado de custo/tempo da execução (T-802/T-805, RF-12). `partial` → laudo parcial honesto.

    Acumulado ao longo do grafo; no fan-out, cada ramo contribui um DELTA (tokens, custo, parcial,
    dimensão degradada) mesclado pelo reducer `merge_budget`. É o registro auditável do consumo
    (vai para `budget_usage` no laudo); a APLICAÇÃO do teto em tempo real é do `BudgetMeter`.

    `started_at` é horário de parede (segundos epoch) — v1.4: o relógio monotônico não é comparável
    entre processos, e o estado é persistido no checkpoint (retomada de HITL em outro processo).
    `accumulated_cost` soma só chamadas com preço conhecido; `unpriced_models` lista as demais.
    """

    model_config = ConfigDict(frozen=True)

    started_at: float = Field(default_factory=time.time)
    input_tokens: int = 0
    output_tokens: int = 0
    accumulated_cost: float = 0.0
    unpriced_models: list[str] = Field(default_factory=list)
    partial: bool = False
    reasons: list[str] = Field(default_factory=list)
    degraded_dims: list[Dimension] = Field(default_factory=list)


def _union[T](a: list[T], b: list[T]) -> list[T]:
    return list(dict.fromkeys([*a, *b]))


def merge_budget(current: BudgetState | None, update: BudgetState) -> BudgetState:
    """Reducer do `budget`: início = mais antigo; consumo somado; partial em OR; listas unidas."""
    if current is None:
        return update
    return BudgetState(
        started_at=min(current.started_at, update.started_at),
        input_tokens=current.input_tokens + update.input_tokens,
        output_tokens=current.output_tokens + update.output_tokens,
        accumulated_cost=current.accumulated_cost + update.accumulated_cost,
        unpriced_models=_union(current.unpriced_models, update.unpriced_models),
        partial=current.partial or update.partial,
        reasons=_union(current.reasons, update.reasons),
        degraded_dims=_union(current.degraded_dims, update.degraded_dims),
    )


class AvaliaState(TypedDict, total=False):
    """Estado compartilhado entre os nós. `total=False`: campos preenchidos ao longo do fluxo."""

    submission: Submission
    inventory: ComponentInventory
    tsm: TargetStaticModel
    classification: TargetClassification
    applicable_dims: list[Dimension]
    effective_weights: WeightProfile
    dimension_results: Annotated[list[DimensionResult], operator.add]
    pending_divergences: list[DivergenceCandidate]
    divergences: list[DivergenceRecord]
    human_decisions: list[HumanDecision]
    comparison: VersionComparison | None
    aggregate: AggregateScore
    budget: Annotated[BudgetState, merge_budget]
    report: EvaluationReport
    status: RunStatus
    error_message: str | None
