"""T-309 — Avaliador de Robustez (RF-DIM-R1/2/3).

Determinístico: retry/fallback (R2), try/except (R1), validação de entrada (R3). Juiz:
significância do tratamento de erro e adequação dos guard-rails anti-injeção. `SEM_FALLBACK_MODELO`
cruza com Custo (RNF-12).
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, TargetClassification
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.base import assemble, make_finding, model_anchor, presence, recommend
from avalia.evaluators.checks import deterministic_outcome
from avalia.judge.base import JudgeContribution

RUBRIC = "robustez/v1"


def evaluate_robustez(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
) -> DimensionResult:
    anchor = model_anchor(tsm)
    findings = []
    recs = []
    has_retry = presence(tsm, "retry")
    has_fallback = presence(tsm, "fallback_modelo")
    has_try = presence(tsm, "try_except")
    has_validation = presence(tsm, "input_validation")

    if not has_retry:
        f = make_finding(
            FindingType.SEM_RETRY,
            Urgency.IMPORTANTE,
            "Sem retry em chamadas externas.",
            "Nenhuma lógica de retry/backoff detectada.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Adicionar retry com backoff", Urgency.IMPORTANTE, f))
    if not has_fallback:
        f = make_finding(
            FindingType.SEM_FALLBACK_MODELO,
            Urgency.IMPORTANTE,
            "Sem fallback de modelo.",
            "Nenhum fallback de modelo/provedor detectado (RNF-12).",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Adicionar fallback de modelo/provedor", Urgency.IMPORTANTE, f))
    if not has_try:
        f = make_finding(
            FindingType.SEM_TRATAMENTO_ERRO,
            Urgency.IMPORTANTE,
            "Sem tratamento de erro estruturado.",
            "Nenhum try/except detectado em torno de chamadas externas.",
            anchor,
        )
        findings.append(f)
        recs.append(
            recommend("Tratar falhas de chamadas externas com try/except", Urgency.IMPORTANTE, f)
        )
    if not has_validation:
        f = make_finding(
            FindingType.SEM_VALIDACAO_ENTRADA,
            Urgency.IMPORTANTE,
            "Sem validação de entrada.",
            "Nenhuma validação de entradas externas detectada.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Validar entradas externas", Urgency.IMPORTANTE, f))
        if tsm.prompts:
            g = make_finding(
                FindingType.GUARDRAIL_INJECAO_AUSENTE,
                Urgency.IMPORTANTE,
                "Sem guard-rail anti-injeção evidente.",
                "Há prompts processando entrada sem validação — risco de injeção de prompt.",
                anchor,
            )
            findings.append(g)
            recs.append(
                recommend("Adicionar guard-rails anti-injeção de prompt", Urgency.IMPORTANTE, g)
            )

    outcomes = [
        deterministic_outcome(
            "R2_retry_fallback",
            passed=has_retry and has_fallback,
            facts={
                "retry": has_retry,
                "fallback": has_fallback,
                "try_except": has_try,
                "validacao": has_validation,
            },
            evidence=[anchor],
        )
    ]
    reasoning = (
        "Sinais determinísticos de robustez (retry, fallback de modelo, try/except, validação) "
        f"avaliados: {len(findings)} lacuna(s)."
    )
    return assemble(
        Dimension.ROBUSTEZ,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=Confidence.ALTO,
        contribution=contribution,
    )
