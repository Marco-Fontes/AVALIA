"""T-309 — Avaliador de Robustez (RF-DIM-R1/2/3).

Determinístico: retry/fallback (R2), try/except (R1), validação de entrada (R3). Juiz:
significância do tratamento de erro e adequação dos guard-rails anti-injeção. `SEM_FALLBACK_MODELO`
cruza com Custo (RNF-12).
"""

from __future__ import annotations

from avalia.config.evaluator_config import DEFAULT_SCORING, ScoringConfig
from avalia.domain.contracts import DimensionResult, TargetClassification
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.base import assemble, make_finding, model_anchor, presence, recommend
from avalia.evaluators.checks import deterministic_outcome
from avalia.extract.secrets import REDACTED, is_sensitive_key
from avalia.judge.base import JudgeContribution

RUBRIC = "robustez/v1"

# SEGREDO_HARDCODED só é escaneado em arquivos de config/dados (onde um segredo literal é leak
# clássico), nunca em código (constante com nome sensível ≠ segredo) nem em workflows de CI
# (credenciais de serviço descartáveis por convenção).
_SECRET_SCANNABLE_EXTS = (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".env")


def _secret_scannable(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    if p.startswith(".github/") or "/.github/" in p:
        return False
    return p.endswith(_SECRET_SCANNABLE_EXTS)


# v1.4 (T-313, DQ-04; RF-DIM-R2, RNF-08): a análise estática vê a PRESENÇA de retry/fallback,
# não a eficácia — ex.: um retry que não captura as exceções reais do provedor passa neste check
# (foi exatamente o caso do próprio AVALIA antes da v1.4). Eficácia só é verificável na Fase 2.
_STATIC_LIMIT = (
    "Fase 1 verifica a PRESENÇA de retry, fallback de modelo, tratamento de erro e validação — "
    "não a EFICÁCIA sob falha real (ex.: se o retry captura as exceções que o provedor de fato "
    "lança). Eficácia só é verificável com execução controlada (Fase 2)."
)


def evaluate_robustez(
    tsm: TargetStaticModel,
    classification: TargetClassification | None = None,
    *,
    contribution: JudgeContribution | None = None,
    scoring: ScoringConfig = DEFAULT_SCORING,
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

    # Fase 1 Tier 1 (harness: Segurança) — segredo hardcoded: chave sensível com valor LITERAL
    # (não vem de env/vault). O mascaramento já marcou o valor como <redacted> justamente porque
    # era literal sensível; valores vindos de os.getenv/${VAR} NÃO são redigidos (ficam de fora).
    # Restrito a ARQUIVOS DE CONFIG/DADOS (não a constantes de código com nome sensível, ex.:
    # `_TOKEN_KEYS = (...)`, nem a credenciais descartáveis de CI) — dogfood mostrou que o nome
    # sozinho era ruidoso demais sobre fonte .py. Valor-literal em .py fica para Tier 2.
    for item in tsm.configs:
        if (
            is_sensitive_key(item.key)
            and item.value_expr == REDACTED
            and _secret_scannable(item.evidence.file_path)
        ):
            s = make_finding(
                FindingType.SEGREDO_HARDCODED,
                Urgency.IMPORTANTE,
                f"Segredo possivelmente hardcoded em `{item.key}`.",
                "Chave sensível com valor literal no código — não vem de variável de ambiente "
                "nem de cofre (menor privilégio; segredo fora do fonte).",
                item.evidence,
            )
            findings.append(s)
            recs.append(
                recommend(
                    f"Mover `{item.key}` para variável de ambiente/cofre (sem hardcode)",
                    Urgency.IMPORTANTE,
                    s,
                )
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
        scoring=scoring,
        applicable=True,
        reasoning=reasoning,
        deterministic_findings=findings,
        recommendations=recs,
        check_outcomes=outcomes,
        base_confidence=Confidence.ALTO,
        contribution=contribution,
        static_limitations=_STATIC_LIMIT,
    )
