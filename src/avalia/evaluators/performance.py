"""T-304 — Avaliador de Performance e Latência (RF-DIM-P1/2).

Determinístico (P2): timeout e streaming. Juiz (P1): serialização desnecessária.
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, TargetClassification
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.base import assemble, make_finding, model_anchor, presence, recommend
from avalia.evaluators.checks import deterministic_outcome
from avalia.judge.base import JudgeContribution

RUBRIC = "performance/v1"


def evaluate_performance(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
) -> DimensionResult:
    anchor = model_anchor(tsm)
    findings = []
    recs = []
    has_timeout = presence(tsm, "timeout")
    has_streaming = presence(tsm, "streaming")

    if not has_timeout:
        f = make_finding(
            FindingType.SEM_TIMEOUT,
            Urgency.IMPORTANTE,
            "Sem timeout em chamadas externas/de modelo.",
            "Nenhum timeout detectado — uma chamada pendurada pode travar o fluxo.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Definir timeout nas chamadas externas", Urgency.IMPORTANTE, f))
    if not has_streaming:
        f = make_finding(
            FindingType.SEM_STREAMING,
            Urgency.SUGESTAO,
            "Sem streaming nas respostas.",
            "Nenhum streaming detectado — latência percebida pode ser maior que o necessário.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Usar streaming onde aplicável", Urgency.SUGESTAO, f))

    outcomes = [
        deterministic_outcome(
            "P2_timeout_streaming",
            passed=has_timeout,
            facts={"timeout": has_timeout, "streaming": has_streaming},
            evidence=[anchor],
        )
    ]
    reasoning = (
        "Sinais determinísticos de performance (timeout, streaming) avaliados: "
        f"{len(findings)} lacuna(s)."
    )
    return assemble(
        Dimension.PERFORMANCE,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=Confidence.ALTO,
        contribution=contribution,
    )
