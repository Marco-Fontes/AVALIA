"""T-307 — Avaliador de Alucinação/Fundamentação (comportamental, RF-DIM-H1/2; RF-13).

Determinístico (parcial): exigência de citação/fonte nos prompts. Juiz (H1): grounding,
abstenção, verificação factual. Declara que a taxa real não é medível na Fase 1 (CA-07).
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, TargetClassification
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.base import assemble, make_finding, project_anchor, prompt_blob, recommend
from avalia.evaluators.checks import deterministic_outcome
from avalia.judge.base import JudgeContribution

RUBRIC = "alucinacao/v1"
_CITATION_TERMS = ("cit", "fonte", "source", "referência", "referencia", "ground", "atribu")
_STATIC_LIMIT = (
    "A taxa real de alucinação não pode ser medida sem execução do sistema-alvo (Fase 2)."
)


def evaluate_alucinacao(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
) -> DimensionResult:
    anchor = tsm.prompts[0].evidence if tsm.prompts else project_anchor(tsm, "prompt")
    findings = []
    recs = []
    blob = prompt_blob(tsm)
    has_citation = any(t in blob for t in _CITATION_TERMS)

    if not has_citation:
        f = make_finding(
            FindingType.PROMPT_SEM_CITACAO,
            Urgency.IMPORTANTE,
            "Prompts não exigem citação de fontes.",
            "Nenhuma exigência de citação/atribuição de origem detectada nos prompts.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Exigir citação de fontes nos prompts", Urgency.IMPORTANTE, f))

    outcomes = [
        deterministic_outcome(
            "H1_citacao", passed=has_citation, facts={"citacao": has_citation}, evidence=[anchor]
        )
    ]
    reasoning = (
        "Mecanismos anti-alucinação avaliados: exigência de citação "
        + ("presente" if has_citation else "ausente")
        + ". Grounding e abstenção são apreciados pelo juiz."
    )
    return assemble(
        Dimension.ALUCINACAO,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=Confidence.MEDIO,
        contribution=contribution,
        static_limitations=_STATIC_LIMIT,
    )
