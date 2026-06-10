"""Contrato `WeightProfile` (perfil de pesos efetivo) — plan §4.

Mora no domínio (sem dependência de config) para que tanto `EvaluatorConfig` (T-005) quanto
o laudo (T-004) e o loader de perfis (T-006) possam referenciá-lo sem ciclo de import.

Rastreabilidade: RF-15, RF-16, RF-17, RF-21.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from avalia.domain.enums import Dimension

_SUM_TOL = 1e-3  # tolerância de "soma 1" (pesos iguais de 7 dims somam 0.999999…)


class WeightSource(StrEnum):
    """Origem do perfil efetivo (RF-16, RF-17)."""

    INFERIDO = "inferido"
    FALLBACK_NEUTRO = "fallback_neutro"
    SOBRESCRITO = "sobrescrito"


class WeightProfile(BaseModel):
    """Pesos por dimensão + origem. `normalized=True` exige soma ≈ 1 (RF-21)."""

    model_config = ConfigDict(frozen=True)

    source: WeightSource
    weights: dict[Dimension, float]
    normalized: bool = True

    @field_validator("weights")
    @classmethod
    def _non_negative(cls, v: dict[Dimension, float]) -> dict[Dimension, float]:
        if not v:
            raise ValueError("WeightProfile.weights não pode ser vazio.")
        bad = {d.value: w for d, w in v.items() if w < 0}
        if bad:
            raise ValueError(f"Pesos negativos não permitidos: {bad}.")
        return v

    @model_validator(mode="after")
    def _check_normalized(self) -> WeightProfile:
        if self.normalized and abs(sum(self.weights.values()) - 1.0) > _SUM_TOL:
            raise ValueError(
                f"Perfil '{self.source.value}' marcado normalized mas soma "
                f"{sum(self.weights.values()):.6f} ≠ 1."
            )
        return self
