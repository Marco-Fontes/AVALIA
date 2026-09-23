"""Contribuição do juiz a uma dimensão (saída do framework T-302, consumida pelos avaliadores).

Separa a opinião semântica (juiz) dos fatos (checks). Carrega substituições de modelo
declaradas (RNF-12), o flag `partial` (fallback esgotado OU teto de orçamento → laudo parcial,
com `partial_reason` distinguindo os dois) e o consumo reportado das chamadas (T-805, DQ-01).

`UsageMeter` é o contrato do medidor de orçamento que o juiz consulta antes de cada chamada;
a implementação (`BudgetMeter`) vive no grafo, que depende do juiz — nunca o contrário.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from avalia.domain.contracts import Finding, JudgeOpinion
from avalia.domain.enums import Confidence


class JudgeContribution(BaseModel):
    """O que o juiz acrescenta a um `DimensionResult`."""

    model_config = ConfigDict(frozen=True)

    opinions: list[JudgeOpinion] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIO
    model_substitutions: list[str] = Field(default_factory=list)  # RNF-12: nunca silencioso
    partial: bool = False
    # v1.4: POR QUE ficou parcial — "fallback" (modelos esgotados, CB-10) ou "budget" (teto, CA-13).
    partial_reason: Literal["fallback", "budget"] | None = None
    budget_detail: str | None = None  # razão do teto atingido, quando partial_reason="budget"
    # v1.4 (T-805): consumo REPORTADO das chamadas bem-sucedidas (cache não consome).
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0  # soma das chamadas com preço conhecido
    unpriced_models: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ChargeResult:
    """Custo de uma chamada: em moeda se o modelo tem preço; senão `None` + o modelo sem preço."""

    cost: float | None
    unpriced_model: str | None = None


class UsageMeter(Protocol):
    """Medidor de orçamento de uma execução (implementado por `graph.budget.BudgetMeter`)."""

    def charge(self, model: str | None, input_tokens: int, output_tokens: int) -> ChargeResult: ...

    def exceeded(self) -> str | None: ...
