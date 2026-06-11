"""N4 `detect_divergence` + reconciliação automática (T-401/T-402, RF-20).

Detecta divergência entre os julgamentos (faixas das `JudgeOpinion`) de uma mesma dimensão, e
tenta reconciliar automaticamente re-julgando com rubrica estrita ancorada no fato do TSM. Gatilho
configurável (resolução #4): faixas qualitativas distintas OU confiança da dimensão < piso.

O score da dimensão NÃO muda (regra 6 — ancorado em fato); a divergência é da camada de opinião.

Rastreabilidade: RF-20; resolução #4; plan §3.6.
"""

from __future__ import annotations

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import (
    DimensionResult,
    DivergenceCandidate,
    DivergenceRecord,
    ResolvedBy,
)
from avalia.domain.tsm import TargetStaticModel
from avalia.judge.contributors import reconcile
from avalia.judge.framework import GatewayLike

BAND_MISMATCH = "band_mismatch"
LOW_CONFIDENCE = "low_confidence"


def detect_candidates(
    results: list[DimensionResult], config: EvaluatorConfig
) -> list[DivergenceCandidate]:
    """Divergência por faixas distintas OU confiança < piso (T-401, resolução #4)."""
    candidates: list[DivergenceCandidate] = []
    for dr in results:
        opinions = list(dr.judge_opinions)
        if len(opinions) < 2:  # divergência exige ≥2 posições em conflito
            continue
        bands = {o.band for o in opinions if o.band is not None}
        band_mismatch = config.divergence.trigger_on_band_mismatch and len(bands) >= 2
        low_conf = dr.confidence.rank < config.divergence.min_confidence.rank
        if band_mismatch or low_conf:
            candidates.append(
                DivergenceCandidate(
                    dimension=dr.dimension,
                    conflicting_positions=opinions,
                    threshold_hit=BAND_MISMATCH if band_mismatch else LOW_CONFIDENCE,
                )
            )
    return candidates


def reconcile_candidate(
    candidate: DivergenceCandidate, *, gateway: GatewayLike, tsm: TargetStaticModel
) -> DivergenceRecord | None:
    """Re-julga estrito; convergência para UMA faixa → resolvido (auto). Senão `None` (persiste)."""
    contribution = reconcile(gateway, candidate.dimension, tsm)
    new_bands = {o.band for o in contribution.opinions if o.band is not None}
    if len(new_bands) == 1:
        band = next(iter(new_bands))
        return DivergenceRecord(
            dimension=candidate.dimension,
            conflicting_positions=candidate.conflicting_positions,
            threshold_hit=candidate.threshold_hit,
            resolved_by=ResolvedBy.AUTO,
            resolution_note=f"Reconciliado automaticamente para a faixa '{band.value}'.",
        )
    return None
