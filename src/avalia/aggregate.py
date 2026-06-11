"""N5 `aggregate` (T-501 + fatia de T-503) — score, veredito e condições de aprovação.

Combinação ponderada (perfil efetivo) → score 0–100 → veredito por faixas (RF-15/RF-18).
Exclui julgamentos abaixo do piso de confiança (RF-22). Na faixa condicional, deriva
`ApprovalCondition` dos achados críticos/importantes, rastreável ao achado (RF-19/CA-09).

Rastreabilidade: RF-15, RF-18, RF-19, RF-22; CA-09. (Priorização completa = T-702/M2.)
"""

from __future__ import annotations

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import (
    AggregateScore,
    ApprovalCondition,
    DimensionResult,
    Finding,
)
from avalia.domain.enums import Dimension, Urgency, Verdict
from avalia.domain.taxonomy import FindingType
from avalia.domain.weights import WeightProfile
from avalia.weights_select import renormalize

_REMEDIATION: dict[FindingType, str] = {
    FindingType.LOOP_SEM_TETO: "Adicionar teto de iteração no nó {node}",
    FindingType.SEM_RETRY: "Adicionar retry/backoff em {node}",
    FindingType.SEM_FALLBACK_MODELO: "Adicionar fallback de modelo em {node}",
    FindingType.SEM_TIMEOUT: "Definir timeout em {node}",
}
_CONDITION_URGENCIES = (Urgency.CRITICO, Urgency.IMPORTANTE)


def _below_floor(dr: DimensionResult, config: EvaluatorConfig) -> bool:
    if config.confidence_floor is None:
        return False
    return dr.confidence.rank < config.confidence_floor.rank


def _condition_for(finding: Finding) -> ApprovalCondition:
    node = finding.evidence[0].symbol
    template = _REMEDIATION.get(finding.finding_type, "Resolver achado: {stmt}")
    return ApprovalCondition(
        statement=template.format(node=node, stmt=finding.statement),
        urgency=finding.urgency,
        traces_to=finding.identity,
    )


_DIM_ORDER = {d: i for i, d in enumerate(Dimension)}
_URGENCY_RANK = {Urgency.CRITICO: 0, Urgency.IMPORTANTE: 1, Urgency.SUGESTAO: 2}


def aggregate(
    results: list[DimensionResult], weights: WeightProfile, config: EvaluatorConfig
) -> AggregateScore:
    # Ordenação estável por Dimension → resultado independe da ordem de chegada do fan-out (T-311).
    ordered = sorted(results, key=lambda dr: _DIM_ORDER[dr.dimension])
    scored = [dr for dr in ordered if dr.applicable and dr.score is not None]
    included = [dr for dr in scored if not _below_floor(dr, config)]
    excluded: list[Dimension] = [dr.dimension for dr in scored if _below_floor(dr, config)]

    if included:
        eff = renormalize(
            {dr.dimension: weights.weights.get(dr.dimension, 0.0) for dr in included},
            [dr.dimension for dr in included],
        )
        score = round(sum((dr.score or 0) * eff[dr.dimension] for dr in included))
    else:
        score = 0
    verdict = config.verdict_for(score)

    conditions: list[ApprovalCondition] = []
    if verdict is Verdict.APROVACAO_CONDICIONAL:
        for dr in included:
            for finding in dr.findings:
                if finding.urgency in _CONDITION_URGENCIES:
                    conditions.append(_condition_for(finding))
        # T-503: priorizadas por urgência (crítico antes de importante)
        conditions.sort(key=lambda c: _URGENCY_RANK[c.urgency])

    return AggregateScore(
        score=score,
        verdict=verdict,
        excluded_low_conf=excluded,
        approval_conditions=conditions,
    )
