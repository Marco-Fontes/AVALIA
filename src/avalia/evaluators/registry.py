"""Registro Dimension → avaliador (fan-out das 7 dimensões, T-311).

Cada avaliador tem assinatura uniforme `(tsm, classification, *, contribution=None)`.
"""

from __future__ import annotations

from collections.abc import Callable

from avalia.domain.contracts import DimensionResult
from avalia.domain.enums import Dimension
from avalia.evaluators.alucinacao import evaluate_alucinacao
from avalia.evaluators.assertividade import evaluate_assertividade
from avalia.evaluators.custo import evaluate_custo
from avalia.evaluators.performance import evaluate_performance
from avalia.evaluators.qualidade import evaluate_qualidade
from avalia.evaluators.robustez import evaluate_robustez
from avalia.evaluators.trajetoria import evaluate_trajetoria

Evaluator = Callable[..., DimensionResult]

EVALUATORS: dict[Dimension, Evaluator] = {
    Dimension.CUSTO: evaluate_custo,
    Dimension.PERFORMANCE: evaluate_performance,
    Dimension.QUALIDADE: evaluate_qualidade,
    Dimension.ASSERTIVIDADE: evaluate_assertividade,
    Dimension.ALUCINACAO: evaluate_alucinacao,
    Dimension.TRAJETORIA: evaluate_trajetoria,
    Dimension.ROBUSTEZ: evaluate_robustez,
}
