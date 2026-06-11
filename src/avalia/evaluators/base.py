"""Scaffold comum dos avaliadores de dimensão (M2). Reduz repetição entre Custo, Performance,
Qualidade, Assertividade, Alucinação e Robustez.

Princípio (regra 6): o SCORE é ancorado nos achados DETERMINÍSTICOS (fato); a contribuição do
juiz acrescenta opiniões/achados semânticos e pode reduzir a confiança, mas não inventa score.
Achados de "ausência" (ex.: sem timeout) ancoram-se numa evidência representativa do projeto,
pois a falta é uma propriedade global — a identidade (RF-29) fica estável por (dim, tipo, arquivo).
"""

from __future__ import annotations

from avalia.domain.contracts import CheckOutcome, DimensionResult, Finding, Recommendation
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.evidence import EvidenceRef
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.judge.base import JudgeContribution

_CRITICAL_PENALTY = 22
_IMPORTANT_PENALTY = 9
_SUGGESTION_PENALTY = 3
_BASE_SCORE = 90


def presence(tsm: TargetStaticModel, kind: str) -> bool:
    """Há algum sinal de robustez/controle do tipo `kind` no TSM?"""
    return any(e.kind == kind for e in tsm.error_handling)


def prompt_blob(tsm: TargetStaticModel) -> str:
    """Texto agregado de prompts + nomes de agentes/ferramentas (busca de termos)."""
    parts = [p.text for p in tsm.prompts]
    parts += [a.name for a in tsm.agents]
    parts += [t.name for t in tsm.tools]
    return " ".join(parts).lower()


def project_anchor(tsm: TargetStaticModel, component_kind: str = "project") -> EvidenceRef:
    """Evidência representativa para achados de ausência (propriedade global do projeto)."""
    file_path = tsm.files[0] if tsm.files else "<projeto>"
    return EvidenceRef(file_path=file_path, symbol="<projeto>", component_kind=component_kind)


def model_anchor(tsm: TargetStaticModel) -> EvidenceRef:
    """Ancora num ponto de chamada de modelo, se houver; senão no projeto."""
    if tsm.model_assignments:
        return tsm.model_assignments[0].evidence
    return project_anchor(tsm, "model_assignment")


def make_finding(
    finding_type: FindingType,
    urgency: Urgency,
    statement: str,
    reasoning: str,
    evidence: EvidenceRef,
) -> Finding:
    return Finding(
        finding_type=finding_type,
        urgency=urgency,
        statement=statement,
        reasoning=reasoning,
        evidence=[evidence],
    )


def recommend(statement: str, urgency: Urgency, finding: Finding) -> Recommendation:
    return Recommendation(statement=statement, urgency=urgency, traces_to=finding.identity)


def score_from_findings(findings: list[Finding]) -> int:
    """Score 0–100 ancorado nos achados determinísticos (fato)."""
    s = _BASE_SCORE
    for f in findings:
        if f.urgency is Urgency.CRITICO:
            s -= _CRITICAL_PENALTY
        elif f.urgency is Urgency.IMPORTANTE:
            s -= _IMPORTANT_PENALTY
        else:
            s -= _SUGGESTION_PENALTY
    return max(0, min(100, s))


def assemble(
    dimension: Dimension,
    *,
    applicable: bool,
    reasoning: str,
    deterministic_findings: list[Finding],
    recommendations: list[Recommendation],
    check_outcomes: list[CheckOutcome],
    base_confidence: Confidence,
    contribution: JudgeContribution | None = None,
    static_limitations: str | None = None,
    confidence_reason: str | None = None,
) -> DimensionResult:
    """Monta o `DimensionResult` dobrando a contribuição do juiz (regra 6)."""
    findings = list(deterministic_findings)
    opinions = []
    substitutions: list[str] = []
    confidence = base_confidence
    if contribution is not None:
        findings += contribution.findings
        opinions += contribution.opinions
        substitutions += contribution.model_substitutions
        confidence = min([base_confidence, contribution.confidence], key=lambda c: c.rank)

    score = score_from_findings(deterministic_findings) if applicable else None
    return DimensionResult(
        dimension=dimension,
        applicable=applicable,
        score=score,
        confidence=confidence,
        confidence_reason=confidence_reason,
        reasoning=reasoning,
        findings=findings,
        recommendations=recommendations,
        check_outcomes=check_outcomes,
        judge_opinions=opinions,
        model_substitutions=list(dict.fromkeys(substitutions)),
        static_limitations=static_limitations,
    )
