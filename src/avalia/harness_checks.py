"""Checks de PRESENÇA de mecanismos de harness — componente declarativo (Fase 1 Tier 2).

Fonte única de verdade de cada check de "o alvo tem o mecanismo X?": o sinal a procurar no TSM
(`ErrorHandling.kind`, extraído deterministicamente), o `FindingType` emitido na ausência, a
dimensão dona, a categoria de harness, a pré-condição (quando o check se aplica) e os textos.

- Os AVALIADORES chamam `presence_findings(tsm, dimension)` para acrescentar os achados da sua
  dimensão — sem `if`s espalhados por avaliador.
- A CAMADA de cobertura (`report/harness.py`) lê `PRESENCE_CHECKS` para registrar categoria +
  pré-condição desses tipos, mantendo coerência entre "emitir achado" e "contar cobertura".

Pré-condições exigem Python no alvo porque a extração destes sinais hoje é do extrator Python
(evita falso positivo em alvo só-TS/JS, onde o mecanismo não é inspecionado). Leitura estática —
nada executa o alvo (RNF-05).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from avalia.domain.contracts import Finding, Recommendation
from avalia.domain.enums import Dimension, HarnessCategory, Urgency
from avalia.domain.evidence import EvidenceRef
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel


def _has_python(tsm: TargetStaticModel) -> bool:
    return any(f.endswith(".py") for f in tsm.files)


def _has_model(tsm: TargetStaticModel) -> bool:
    return bool(tsm.model_assignments) or bool(tsm.agents)


def _has_graph(tsm: TargetStaticModel) -> bool:
    return bool(tsm.edges) or bool(tsm.agents)


# Pré-condições nomeadas (fonte única; a camada de cobertura delega a estas).
PRECONDITIONS: dict[str, Callable[[TargetStaticModel], bool]] = {
    "py_model": lambda t: _has_python(t) and _has_model(t),
    "py_graph": lambda t: _has_python(t) and _has_graph(t),
}


def precondition_met(key: str, tsm: TargetStaticModel) -> bool:
    fn = PRECONDITIONS.get(key)
    return bool(fn and fn(tsm))


@dataclass(frozen=True)
class HarnessPresenceCheck:
    """Um check declarativo de presença de mecanismo (ausência → achado determinístico)."""

    signal: str  # ErrorHandling.kind procurado no TSM
    finding_type: FindingType
    dimension: Dimension  # dimensão dona (onde o achado penaliza o score interno)
    category: HarnessCategory  # categoria de harness exibida
    precondition: str  # chave em PRECONDITIONS
    urgency: Urgency
    statement: str
    reasoning: str
    recommendation: str


PRESENCE_CHECKS: tuple[HarnessPresenceCheck, ...] = (
    HarnessPresenceCheck(
        signal="structured_output",
        finding_type=FindingType.SEM_SAIDA_ESTRUTURADA,
        dimension=Dimension.ROBUSTEZ,
        category=HarnessCategory.SAIDAS_VERIFICACAO,
        precondition="py_model",
        urgency=Urgency.IMPORTANTE,
        statement="Saída do modelo sem schema estruturado forçado.",
        reasoning="Nenhum structured output / JSON Schema forçado detectado "
        "(with_structured_output / response_format / schema) — saída que alimenta código "
        "pode vir malformada.",
        recommendation="Forçar saída estruturada (with_structured_output/response_format/schema)",
    ),
    HarnessPresenceCheck(
        signal="prompt_cache",
        finding_type=FindingType.SEM_PROMPT_CACHE,
        dimension=Dimension.CUSTO,
        category=HarnessCategory.CONTEXTO,
        precondition="py_model",
        urgency=Urgency.SUGESTAO,
        statement="Sem prompt caching nas chamadas de modelo.",
        reasoning="Nenhum cache_control detectado — o prefixo estável (system/tools) não é "
        "cacheado, elevando custo e latência.",
        recommendation="Usar prompt caching (cache_control) no prefixo estável",
    ),
    HarnessPresenceCheck(
        signal="checkpoint",
        finding_type=FindingType.SEM_CHECKPOINT_ESTADO,
        dimension=Dimension.ROBUSTEZ,
        category=HarnessCategory.EXECUCAO_DURAVEL,
        precondition="py_graph",
        urgency=Urgency.IMPORTANTE,
        statement="Sem checkpoint de estado no fluxo de agente.",
        reasoning="Nenhum checkpointer/persistência de estado detectado — um crash perde o "
        "progresso e não há retomada.",
        recommendation="Adicionar checkpointer (persistência de estado por passo)",
    ),
    HarnessPresenceCheck(
        signal="observability",
        finding_type=FindingType.SEM_OBSERVABILIDADE,
        dimension=Dimension.PERFORMANCE,
        category=HarnessCategory.OBSERVABILIDADE,
        precondition="py_model",
        # Sugestão (não reprova): a detecção estática de observabilidade é incompleta —
        # instrumentação custom é invisível —, então a ausência é um nudge, não um veredito.
        urgency=Urgency.SUGESTAO,
        statement="Sem observabilidade padrão detectada (tracing/logging).",
        reasoning="Nenhum logging/tracing/instrumentação detectado — sem isso não se depura "
        "nem se mede o agente em produção.",
        recommendation="Instrumentar com logging/tracing (ex.: OpenTelemetry) nas chamadas",
    ),
)


def _anchor(tsm: TargetStaticModel) -> EvidenceRef:
    """Evidência representativa para achados de ausência (propriedade global do projeto)."""
    if tsm.model_assignments:
        return tsm.model_assignments[0].evidence
    file_path = tsm.files[0] if tsm.files else "<projeto>"
    return EvidenceRef(file_path=file_path, symbol="<projeto>", component_kind="project")


def presence_findings(
    tsm: TargetStaticModel, dimension: Dimension
) -> tuple[list[Finding], list[Recommendation]]:
    """Achados+recomendações dos checks de presença da `dimension` cujo mecanismo está ausente."""
    anchor = _anchor(tsm)
    present = {e.kind for e in tsm.error_handling}
    findings: list[Finding] = []
    recs: list[Recommendation] = []
    for c in PRESENCE_CHECKS:
        if c.dimension is not dimension:
            continue
        if not precondition_met(c.precondition, tsm):
            continue
        if c.signal in present:
            continue
        f = Finding(
            finding_type=c.finding_type,
            urgency=c.urgency,
            statement=c.statement,
            reasoning=c.reasoning,
            evidence=[anchor],
        )
        findings.append(f)
        recs.append(
            Recommendation(statement=c.recommendation, urgency=c.urgency, traces_to=f.identity)
        )
    return findings, recs
