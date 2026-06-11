"""T-305 — Avaliador de Qualidade e Correção (comportamental, RF-DIM-Q1/2; RF-13).

Determinístico (Q1): existência de harness de verificação. Sem harness → confiança BAIXA com
justificativa (CA-06). Juiz: clareza dos prompts e rubricas. Declara `static_limitations` (RF-13).
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, TargetClassification
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.base import assemble, make_finding, project_anchor, recommend
from avalia.evaluators.checks import deterministic_outcome
from avalia.judge.base import JudgeContribution

RUBRIC = "qualidade/v1"
_STATIC_LIMIT = (
    "A Fase 1 avalia a presença e adequação de mecanismos de verificação (harness, rubricas), "
    "não a correção real das saídas — isso requer execução (Fase 2)."
)


def evaluate_qualidade(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
) -> DimensionResult:
    anchor = project_anchor(tsm)
    findings = []
    recs = []
    confidence = Confidence.MEDIO
    confidence_reason = None

    if not tsm.has_harness:
        f = make_finding(
            FindingType.SEM_HARNESS_VERIFICACAO,
            Urgency.IMPORTANTE,
            "Sem harness de testes/avaliação.",
            "Nenhum harness de verificação detectado nos artefatos.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Adicionar harness de testes/avaliação", Urgency.IMPORTANTE, f))
        confidence = Confidence.BAIXO
        confidence_reason = (
            "Ausência de harness de testes impede avaliar a maquinaria de verificação (CA-06)."
        )

    outcomes = [
        deterministic_outcome(
            "Q1_harness",
            passed=tsm.has_harness,
            facts={"harness": tsm.has_harness},
            evidence=[anchor],
        )
    ]
    reasoning = (
        "Maquinaria de verificação avaliada: harness "
        + ("presente" if tsm.has_harness else "ausente")
        + ". Clareza de prompts/rubricas é apreciada pelo juiz."
    )
    return assemble(
        Dimension.QUALIDADE,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=confidence,
        contribution=contribution,
        static_limitations=_STATIC_LIMIT,
        confidence_reason=confidence_reason,
    )
