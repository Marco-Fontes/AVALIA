"""Contribuição do juiz a uma dimensão (saída do framework T-302, consumida pelos avaliadores).

Separa a opinião semântica (juiz) dos fatos (checks). Carrega substituições de modelo
declaradas (RNF-12) e o flag `partial` (fallback esgotado → laudo parcial).
"""

from __future__ import annotations

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
