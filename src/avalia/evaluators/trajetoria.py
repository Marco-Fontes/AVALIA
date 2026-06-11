"""T-308 — Avaliador da dimensão Trajetória (RF-DIM-T*).

M1: ancorado no FATO determinístico T3 (loop sem teto) — veredito governado pelo fato, não
pela opinião (plan §6.3). Um loop sem teto é `LOOP_SEM_TETO` (crítico) e empurra o score para
a faixa condicional (50–74), gerando recomendação rastreável (suporta CA-09). Opinião
semântica do juiz (T1 clareza de ferramenta) é DOBRADA quando fornecida (T-302), nunca
substituindo o fato.

Trajetória NÃO é dimensão comportamental → não exige `static_limitations`.

Rastreabilidade: RF-DIM-T1/T2/T3, RF-09..11, RF-14, RF-27; CA-09.
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, Finding, Recommendation
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.checks import deterministic_outcome
from avalia.judge.base import JudgeContribution

TRAJETORIA_RUBRIC = "trajetoria/v1"
_NO_CAP_PENALTY = 25
_BASE_SCORE = 85


def evaluate_trajetoria(
    tsm: TargetStaticModel, contribution: JudgeContribution | None = None
) -> DimensionResult:
    uncapped = [loop for loop in tsm.loops if not loop.has_cap]

    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    for loop in uncapped:
        node = loop.evidence.symbol
        finding = Finding(
            finding_type=FindingType.LOOP_SEM_TETO,
            urgency=Urgency.CRITICO,
            statement=f"Loop sem teto de iteração no nó {node}.",
            reasoning=loop.cap_reason or "Loop sem limite de iteração nem condição de parada.",
            evidence=[loop.evidence],
        )
        findings.append(finding)
        recommendations.append(
            Recommendation(
                statement=f"Adicionar teto de iteração no nó {node}",
                urgency=Urgency.CRITICO,
                traces_to=finding.identity,
            )
        )

    loop_facts = sorted([loop.evidence.symbol, loop.has_cap] for loop in tsm.loops)
    outcomes = [
        deterministic_outcome(
            "T3_loop_cap",
            passed=not uncapped,
            facts=loop_facts,
            evidence=[loop.evidence for loop in uncapped],
        )
    ]

    # Score ancorado em fato: loop sem teto → faixa condicional (50–74).
    score = _BASE_SCORE
    if uncapped:
        score = max(50, _BASE_SCORE - _NO_CAP_PENALTY * len(uncapped))
    confidence = Confidence.ALTO  # veredito governado por fato determinístico

    if uncapped:
        reasoning = (
            f"{len(uncapped)} loop(s) sem teto de iteração detectado(s) deterministicamente "
            "no TSM — fato, não opinião. Sem limite explícito, o fluxo pode não terminar, o "
            "que rebaixa a trajetória para a faixa de aprovação condicional."
        )
    else:
        reasoning = (
            "Nenhum loop sem teto detectado; os loops presentes têm limite explícito e o "
            "roteamento estático não revela caminhos mortos óbvios."
        )

    opinions = list(contribution.opinions) if contribution else []
    if contribution:
        findings.extend(contribution.findings)
    substitutions = list(contribution.model_substitutions) if contribution else []

    return DimensionResult(
        dimension=Dimension.TRAJETORIA,
        applicable=True,
        score=score,
        confidence=confidence,
        reasoning=reasoning,
        findings=findings,
        recommendations=recommendations,
        check_outcomes=outcomes,
        judge_opinions=opinions,
        model_substitutions=substitutions,
    )
