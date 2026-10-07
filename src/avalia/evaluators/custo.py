"""T-303 — Avaliador de Custo e Eficiência (RF-DIM-C1/2/3).

Determinístico (C2): limite de tokens, cache, teto de loop. Juiz (C1/C3): adequação do mix de
modelos e redundância. `SEM_FALLBACK_MODELO` cruza com Robustez (RNF-12).
"""

from __future__ import annotations

import re

from avalia.config.evaluator_config import DEFAULT_SCORING, ScoringConfig
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
from avalia.extract.contradictions import detect_contradictions
from avalia.judge.base import JudgeContribution

RUBRIC = "custo/v1"

# Fase 1 Tier 1 (harness: Ciclo de vida) — detecção conservadora de alias móvel de modelo.
# Exige família de modelo reconhecida E sufixo móvel ("latest") → baixíssimo ruído (não pega
# tags de docker como "python:3.12-latest", nem slugs sem data como "gpt-4o").
_MODEL_FAMILY = re.compile(
    r"\b(gpt|claude|gemini|llama|mistral|command|deepseek|qwen|grok|o1|o3)\b", re.IGNORECASE
)


def _is_moving_model_alias(expr: str) -> bool:
    text = expr.strip().strip("'\"").lower()
    return "latest" in text and text.endswith("latest") and bool(_MODEL_FAMILY.search(text))


def evaluate_custo(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
    scoring: ScoringConfig = DEFAULT_SCORING,
) -> DimensionResult:
    anchor = model_anchor(tsm)
    findings = []
    recs = []
    has_token_limit = presence(tsm, "token_limit")
    has_cache = presence(tsm, "cache")
    has_fallback = presence(tsm, "fallback_modelo")
    # Laço de serviço/stream roda sem teto por design — custo contínuo de operação, não "custo
    # ilimitado por iteração descontrolada". Excluído do achado SEM_TETO_CUSTO (T4.1b).
    uncapped = [loop for loop in tsm.loops if not loop.has_cap and not loop.service]

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

    # Fase 1 Tier 1 (harness: Ciclo de vida) — modelo em alias móvel (sem versão fixa).
    for item in tsm.configs:
        if _is_moving_model_alias(item.value_expr):
            m = make_finding(
                FindingType.MODELO_SEM_VERSAO_FIXA,
                Urgency.IMPORTANTE,
                f"Modelo em alias móvel (sem versão fixa) em `{item.key}`.",
                "O slug aponta para um alias móvel (ex.: '-latest'); o provedor pode trocar o "
                "modelo sem aviso, causando regressão silenciosa sem eval.",
                item.evidence,
            )
            findings.append(m)
            recs.append(
                recommend(f"Fixar a versão do modelo em `{item.key}`", Urgency.IMPORTANTE, m)
            )

    # T-106: contradições modelo declarado≠usado (dimensão dona = Custo, regra 4) — CB-08.
    contradictions = [f for f in detect_contradictions(tsm) if f.dimension is Dimension.CUSTO]
    for f in contradictions:
        findings.append(f)
        recs.append(
            recommend(
                "Alinhar o modelo declarado na config com o usado no código", Urgency.IMPORTANTE, f
            )
        )

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
    base_conf = Confidence.MEDIO if contradictions else Confidence.ALTO
    conf_reason = (
        "Contradição config↔código (modelo declarado≠usado) reduz a confiança (CB-08)."
        if contradictions
        else None
    )
    return assemble(
        Dimension.CUSTO,
        scoring=scoring,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=base_conf,
        confidence_reason=conf_reason,
        contribution=contribution,
    )
