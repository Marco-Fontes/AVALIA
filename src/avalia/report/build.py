"""N7 `build_report` (T-701) — monta o `EvaluationReport` completo (blocos 4.2.1–4.2.8).

Cabeçalho (classificação/perfil/veredito/confiança), dimensões, recomendações consolidadas
(fatia de T-702), condições de aprovação, divergências (vazio no M1), cobertura/limitações e
metadados com substituições de modelo declaradas (RNF-12). Autocontido para auditoria (RNF-10).

Rastreabilidade: RF-25, RF-27, RNF-08, RNF-10; Seção 4.2.
"""

from __future__ import annotations

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import (
    AggregateScore,
    ComponentInventory,
    DimensionResult,
    DivergenceRecord,
    EvaluationReport,
    Recommendation,
    ReportHeader,
    ReportMetadata,
    ResolvedBy,
    TargetClassification,
    VersionComparison,
)
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.tsm import TargetStaticModel
from avalia.domain.weights import WeightProfile

_URGENCY_ORDER = {Urgency.CRITICO: 0, Urgency.IMPORTANTE: 1, Urgency.SUGESTAO: 2}
_DIM_ORDER = {d: i for i, d in enumerate(Dimension)}
_CONF_ORDER = [Confidence.BAIXO, Confidence.MEDIO, Confidence.ALTO]


def _reduce_confidence(conf: Confidence) -> Confidence:
    return _CONF_ORDER[max(0, _CONF_ORDER.index(conf) - 1)]


def _apply_divergence_confidence(
    results: list[DimensionResult], divergences: list[DivergenceRecord]
) -> list[DimensionResult]:
    """Divergência escalada ao humano reduz a confiança reportada da dimensão (decisão M3)."""
    escalated = {d.dimension for d in divergences if d.resolved_by is ResolvedBy.HUMANO}
    if not escalated:
        return results
    out: list[DimensionResult] = []
    for dr in results:
        if dr.dimension in escalated and dr.confidence is not Confidence.BAIXO:
            note = "Confiança reduzida: divergência de julgamento resolvida por decisão humana."
            out.append(
                dr.model_copy(
                    update={
                        "confidence": _reduce_confidence(dr.confidence),
                        "confidence_reason": note,
                    }
                )
            )
        else:
            out.append(dr)
    return out


def _overall_confidence(
    results: list[DimensionResult], classification: TargetClassification
) -> Confidence:
    confs = [dr.confidence for dr in results]
    if not confs:
        return classification.classification_conf
    return min(confs, key=lambda c: c.rank)


def _consolidate_recommendations(results: list[DimensionResult]) -> list[Recommendation]:
    seen: dict[str, Recommendation] = {}
    for dr in results:
        for rec in dr.recommendations:
            seen.setdefault(rec.statement, rec)
    return sorted(seen.values(), key=lambda r: _URGENCY_ORDER[r.urgency])


def build_report(
    *,
    classification: TargetClassification,
    weights: WeightProfile,
    aggregate_score: AggregateScore,
    results: list[DimensionResult],
    inventory: ComponentInventory,
    tsm: TargetStaticModel,
    config: EvaluatorConfig,
    divergences: list[DivergenceRecord] | None = None,
    comparison: VersionComparison | None = None,
    no_history_note: bool = False,
) -> EvaluationReport:
    divergences = divergences or []
    # Divergência escalada ao humano reduz a confiança reportada da dimensão (M3, regra 6).
    results = _apply_divergence_confidence(results, divergences)

    header = ReportHeader(
        classification=classification,
        effective_weights=weights,
        verdict=aggregate_score.verdict,
        score=aggregate_score.score,
        confidence=_overall_confidence(results, classification),
    )

    substitutions = [s for dr in results for s in dr.model_substitutions]
    known_limitations = list(classification.caveats)
    if tsm.coverage.sampled:
        known_limitations.append(
            f"Arquivos não analisados a fundo (best-effort): {', '.join(tsm.coverage.sampled)}."
        )
    if tsm.readability.unreadable_files:
        known_limitations.append(
            "Há arquivos ilegíveis; dimensões afetadas têm confiança reduzida."
        )
    escalated = sorted(
        {d.dimension.value for d in divergences if d.resolved_by is ResolvedBy.HUMANO}
    )
    if escalated:
        known_limitations.append(
            f"Divergências de julgamento resolvidas por humano em: {', '.join(escalated)}."
        )
    if no_history_note:
        known_limitations.append(
            "Sem versão anterior deste alvo; comparação histórica não disponível (CB-06)."
        )

    metadata = ReportMetadata(
        effective_config=config,
        inventory=inventory,
        coverage=tsm.coverage,
        readability=tsm.readability,
        known_limitations=known_limitations,
        model_substitutions=list(dict.fromkeys(substitutions)),
    )

    # Ordenação estável por Dimension → laudo independe da ordem de chegada do fan-out (T-311).
    ordered = sorted(results, key=lambda dr: _DIM_ORDER[dr.dimension])
    sorted_divergences = sorted(divergences, key=lambda d: _DIM_ORDER[d.dimension])
    return EvaluationReport(
        header=header,
        dimensions=ordered,
        consolidated_recommendations=_consolidate_recommendations(results),
        approval_conditions=aggregate_score.approval_conditions,
        comparison=comparison,
        divergences=sorted_divergences,
        metadata=metadata,
    )
