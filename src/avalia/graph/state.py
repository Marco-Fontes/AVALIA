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
    """Estado de custo/tempo da execução (T-802/RF-12). `partial` sinaliza laudo parcial honesto.

    Acumulado ao longo do grafo; no fan-out, cada ramo pode contribuir um delta (custo/parcial)
    mesclado pelo reducer `merge_budget`. `started_monotonic` é a âncora de tempo decorrido.
    """

    model_config = ConfigDict(frozen=True)

    started_monotonic: float = Field(default_factory=time.monotonic)
    accumulated_cost: float = 0.0
    partial: bool = False
    reasons: list[str] = Field(default_factory=list)


def merge_budget(current: BudgetState | None, update: BudgetState) -> BudgetState:
    """Reducer do `budget`: tempo = mais antigo; custo somado; partial em OR; razões unidas."""
    if current is None:
        return update
    return BudgetState(
        started_monotonic=min(current.started_monotonic, update.started_monotonic),
        accumulated_cost=current.accumulated_cost + update.accumulated_cost,
        partial=current.partial or update.partial,
        reasons=list(dict.fromkeys([*current.reasons, *update.reasons])),
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
