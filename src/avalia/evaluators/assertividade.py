"""T-306 — Avaliador de Assertividade (comportamental, RF-DIM-A1/2; RF-13).

Determinístico (A2): presença de ramo de escalonamento/tratamento de baixa confiança. Juiz
(A1): se os prompts pedem expressão de confiança. Declara `static_limitations` (RF-13).
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, TargetClassification
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.base import assemble, make_finding, project_anchor, prompt_blob, recommend
from avalia.evaluators.checks import deterministic_outcome
from avalia.judge.base import JudgeContribution

RUBRIC = "assertividade/v1"
_ESCALATION_TERMS = ("escal", "human", "aprova", "approval", "incerteza", "confian", "confidence")
_STATIC_LIMIT = (
    "A Fase 1 avalia a presença de mecanismos de expressão e tratamento de confiança, não o "
    "comportamento real de calibração — isso requer execução (Fase 2)."
)


def evaluate_assertividade(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
) -> DimensionResult:
    anchor = project_anchor(tsm)
    findings = []
    recs = []
    blob = prompt_blob(tsm)
    has_escalation = any(t in blob for t in _ESCALATION_TERMS)

    if not has_escalation:
        f = make_finding(
            FindingType.SEM_ESCALONAMENTO_BAIXA_CONFIANCA,
            Urgency.IMPORTANTE,
            "Sem ramo de escalonamento para baixa confiança.",
            "Nenhum sinal de escalonamento/aprovação humana ao detectar baixa confiança.",
            anchor,
        )
        findings.append(f)
        recs.append(
            recommend("Adicionar escalonamento ao detectar baixa confiança", Urgency.IMPORTANTE, f)
        )

    outcomes = [
        deterministic_outcome(
            "A2_escalonamento",
            passed=has_escalation,
            facts={"escalonamento": has_escalation},
            evidence=[anchor],
        )
    ]
    reasoning = (
        "Tratamento de baixa confiança avaliado: escalonamento "
        + ("presente" if has_escalation else "ausente")
        + ". A expressão de confiança nos prompts é apreciada pelo juiz."
    )
    return assemble(
        Dimension.ASSERTIVIDADE,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=Confidence.MEDIO,
        contribution=contribution,
        static_limitations=_STATIC_LIMIT,
    )
