"""N3 `select_weights` (T-204) — dimensões aplicáveis + perfil + renormalização.

Seleciona o perfil pelo tipo inferido (se confiança ≥ piso) ou **fallback neutro**; aplica
**sobrescrita** do usuário (RF-17); marca dimensões inaplicáveis (M1: nenhuma) e **renormaliza**
os pesos das aplicáveis para somar 1 (RF-21, CA-08).

Rastreabilidade: RF-16, RF-17, RF-21; CA-04, CA-08, CB-09.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import TargetClassification
from avalia.domain.enums import Confidence, Dimension
from avalia.domain.weights import WeightProfile, WeightSource


class WeightSelection(BaseModel):
    """Resultado de N3: perfil efetivo + dimensões aplicáveis (+ razões de inaplicável)."""

    model_config = ConfigDict(frozen=True)

    profile: WeightProfile
    applicable_dims: list[Dimension]
    inapplicable_reasons: dict[Dimension, str] = Field(default_factory=dict)


def renormalize(
    weights: dict[Dimension, float], applicable: list[Dimension]
) -> dict[Dimension, float]:
    """Restringe às dimensões aplicáveis e renormaliza para somar 1 (RF-21)."""
    subset = {d: weights.get(d, 0.0) for d in applicable}
    total = sum(subset.values())
    if total <= 0:
        equal = 1.0 / len(applicable)
        return dict.fromkeys(applicable, equal)
    return {d: w / total for d, w in subset.items()}


def select_weights(
    classification: TargetClassification,
    config: EvaluatorConfig,
    profiles: dict[str, WeightProfile],
) -> WeightSelection:
    # M1: todas as 7 dimensões aplicáveis (inaplicabilidade fina entra com o fan-out, M2).
    applicable = list(Dimension)

    if config.weights is not None:
        base = config.weights
        source = WeightSource.SOBRESCRITO
    elif (
        classification.system_type
        and classification.classification_conf.rank >= Confidence.MEDIO.rank
        and classification.system_type in profiles
    ):
        base = profiles[classification.system_type].weights
        source = WeightSource.INFERIDO
    else:
        base = profiles["neutro"].weights
        source = WeightSource.FALLBACK_NEUTRO

    weights = renormalize(base, applicable)
    return WeightSelection(
        profile=WeightProfile(source=source, weights=weights, normalized=True),
        applicable_dims=applicable,
    )
