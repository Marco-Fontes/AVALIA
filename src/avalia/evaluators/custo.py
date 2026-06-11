"""T-303 — Avaliador de Custo e Eficiência (RF-DIM-C1/2/3).

Determinístico (C2): limite de tokens, cache, teto de loop. Juiz (C1/C3): adequação do mix de
modelos e redundância. `SEM_FALLBACK_MODELO` cruza com Robustez (RNF-12).
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, TargetClassification
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.base import (
    assemble,
    make_finding,
    model_anchor,
    presence,
    recommend,
)
from avalia.evaluators.checks import deterministic_outcome
from avalia.judge.base import JudgeContribution

RUBRIC = "custo/v1"


def evaluate_custo(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
) -> DimensionResult:
    anchor = model_anchor(tsm)
    findings = []
    recs = []
    has_token_limit = presence(tsm, "token_limit")
    has_cache = presence(tsm, "cache")
    has_fallback = presence(tsm, "fallback_modelo")
    uncapped = [loop for loop in tsm.loops if not loop.has_cap]

    if not has_token_limit:
        f = make_finding(
            FindingType.SEM_LIMITE_TOKENS,
            Urgency.IMPORTANTE,
            "Sem limite de tokens nas chamadas de modelo.",
            "Nenhum max_tokens detectado — custo por chamada é ilimitado.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Definir max_tokens nas chamadas de modelo", Urgency.IMPORTANTE, f))
    if not has_cache:
        f = make_finding(
            FindingType.SEM_CACHE,
            Urgency.SUGESTAO,
            "Sem cache de chamadas.",
            "Nenhum cache detectado — chamadas repetidas recomputam.",
            anchor,
        )
        findings.append(f)
        recs.append(recommend("Adicionar cache para chamadas repetidas", Urgency.SUGESTAO, f))
    # A AUSÊNCIA de fallback de modelo é achado de Robustez (SEM_FALLBACK_MODELO, regra 4);
    # aqui entra só como fato no check (afeta custo/disponibilidade — C1, cruza com RF-DIM-R2).
    if uncapped:
        f = make_finding(
            FindingType.SEM_TETO_CUSTO,
            Urgency.IMPORTANTE,
            f"Loop sem teto pode gerar custo ilimitado em {uncapped[0].evidence.symbol}.",
            "Loop sem limite de iteração — custo de modelo dentro do loop é ilimitado.",
            uncapped[0].evidence,
        )
        findings.append(f)
        recs.append(recommend("Limitar iterações do loop para conter custo", Urgency.IMPORTANTE, f))

    outcomes = [
        deterministic_outcome(
            "C2_controles_custo",
            passed=has_token_limit and not uncapped,
            facts={
                "token_limit": has_token_limit,
                "cache": has_cache,
                "fallback": has_fallback,
                "loops_sem_teto": len(uncapped),
            },
            evidence=[anchor],
        )
    ]
    reasoning = (
        "Controles de custo avaliados deterministicamente (limite de tokens, cache, fallback de "
        f"modelo, teto de loop): {len(findings)} lacuna(s) encontrada(s)."
    )
    return assemble(
        Dimension.CUSTO,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=Confidence.ALTO,
        contribution=contribution,
    )
