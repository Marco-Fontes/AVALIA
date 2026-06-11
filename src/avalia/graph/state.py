"""Estado do grafo `AvaliaState` (plan §3.3). TypedDict com reducer no fan-out.

`dimension_results` usa `operator.add` para o fan-out paralelo das dimensões (M2) escrever sem
corrida; no M1 só a Trajetória escreve. Demais campos são `replace`.

Rastreabilidade: plan §3.3; RF-01, RF-04..08, RF-09..14, RF-15..22.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

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
    report: EvaluationReport
    status: RunStatus
    error_message: str | None
