"""Fase 0 — CAMADA de cobertura de harness (projeção sobre as 7 dimensões).

NÃO altera o motor: lê os achados/fatos que os avaliadores já produzem e os reprojeta nas
categorias de harness de produção que o time usa como checklist. O número
"Cobertura de harness — análise estática" é honesto (0–100 = checks aplicáveis sem achado ÷
aplicáveis) e naturalmente sem teto — 100 = tudo que sabemos checar estaticamente está presente.

Cada `FindingType` tem UMA categoria primária, uma pré-condição (o componente do alvo que torna
o check aplicável) e um flag determinístico/juiz (checks de juiz só contam com `--llm`). Categorias
sem check aplicável nesta fase/modo aparecem como n/a — declaradas, fora do denominador.
"""

from __future__ import annotations

from avalia.domain.contracts import (
    DimensionResult,
    Finding,
    HarnessCategoryCoverage,
    HarnessCoverageReport,
)
from avalia.domain.enums import Confidence, HarnessCategory
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel

# Ordem e rótulo de exibição (mantém a numeração do checklist de origem — 13/15/17 excluídas).
CATEGORY_META: tuple[tuple[HarnessCategory, int, str], ...] = (
    (HarnessCategory.ORQUESTRACAO, 1, "Orquestração e controle do loop"),
    (HarnessCategory.CONTEXTO, 2, "Engenharia de contexto"),
    (HarnessCategory.MEMORIA, 3, "Memória estruturada"),
    (HarnessCategory.FERRAMENTAS, 4, "Ferramentas"),
    (HarnessCategory.SKILLS, 5, "Skills e conhecimento procedural"),
    (HarnessCategory.MULTIAGENTE, 6, "Multiagente e subagentes"),
    (HarnessCategory.RESILIENCIA, 7, "Resiliência de modelo e infraestrutura"),
    (HarnessCategory.SAIDAS_VERIFICACAO, 8, "Saídas estruturadas e verificação"),
    (HarnessCategory.SEGURANCA, 9, "Segurança e guardrails"),
    (HarnessCategory.OBSERVABILIDADE, 10, "Observabilidade"),
    (HarnessCategory.AVALIACAO_CONTINUA, 11, "Avaliação e qualidade contínua"),
    (HarnessCategory.EXECUCAO_DURAVEL, 12, "Execução durável e assíncrona"),
    (HarnessCategory.CICLO_DE_VIDA, 14, "Gestão de ciclo de vida"),
    (HarnessCategory.CUSTO_PERFORMANCE, 16, "Custo e performance"),
)

# Pré-condições: o componente do alvo que torna um check aplicável.
_MODEL, _TOOLS, _LOOPS, _EDGES, _PROMPTS, _ALWAYS = (
    "model",
    "tools",
    "loops",
    "edges",
    "prompts",
    "always",
)

# FindingType → (categoria primária, pré-condição, determinístico?). Checks de juiz (det=False)
# só contam para a cobertura quando o laudo rodou com `--llm`.
_FINDING_SPEC: dict[FindingType, tuple[HarnessCategory, str, bool]] = {
    FindingType.MIX_MODELO_INADEQUADO: (HarnessCategory.RESILIENCIA, _MODEL, False),
    FindingType.SEM_LIMITE_TOKENS: (HarnessCategory.CUSTO_PERFORMANCE, _MODEL, True),
    FindingType.SEM_TETO_CUSTO: (HarnessCategory.CUSTO_PERFORMANCE, _LOOPS, True),
    FindingType.CHAMADAS_REDUNDANTES: (HarnessCategory.CUSTO_PERFORMANCE, _MODEL, False),
    FindingType.SEM_CACHE: (HarnessCategory.CUSTO_PERFORMANCE, _MODEL, True),
    FindingType.SERIALIZACAO_DESNECESSARIA: (HarnessCategory.CUSTO_PERFORMANCE, _MODEL, False),
    FindingType.SEM_TIMEOUT: (HarnessCategory.RESILIENCIA, _MODEL, True),
    FindingType.SEM_STREAMING: (HarnessCategory.CUSTO_PERFORMANCE, _MODEL, True),
    FindingType.SEM_HARNESS_VERIFICACAO: (HarnessCategory.AVALIACAO_CONTINUA, _ALWAYS, True),
    FindingType.RUBRICA_AUSENTE_OU_VAGA: (HarnessCategory.AVALIACAO_CONTINUA, _ALWAYS, False),
    FindingType.PROMPT_AMBIGUO: (HarnessCategory.CONTEXTO, _PROMPTS, False),
    FindingType.SEM_EXPRESSAO_CONFIANCA: (HarnessCategory.SAIDAS_VERIFICACAO, _PROMPTS, False),
    FindingType.SEM_ESCALONAMENTO_BAIXA_CONFIANCA: (HarnessCategory.RESILIENCIA, _MODEL, True),
    FindingType.PROMPT_SEM_CITACAO: (HarnessCategory.SAIDAS_VERIFICACAO, _PROMPTS, True),
    FindingType.SEM_GROUNDING: (HarnessCategory.SAIDAS_VERIFICACAO, _PROMPTS, False),
    FindingType.SEM_ABSTENCAO: (HarnessCategory.SAIDAS_VERIFICACAO, _PROMPTS, False),
    FindingType.SEM_VERIFICACAO_FATUAL: (HarnessCategory.SAIDAS_VERIFICACAO, _MODEL, False),
    FindingType.LOOP_SEM_TETO: (HarnessCategory.ORQUESTRACAO, _LOOPS, True),
    FindingType.CAMINHO_MORTO: (HarnessCategory.ORQUESTRACAO, _EDGES, True),
    FindingType.PASSOS_REDUNDANTES: (HarnessCategory.ORQUESTRACAO, _EDGES, False),
    FindingType.FERRAMENTA_SEM_DESCRICAO: (HarnessCategory.FERRAMENTAS, _TOOLS, True),
    FindingType.ROTEAMENTO_INCOERENTE: (HarnessCategory.ORQUESTRACAO, _EDGES, False),
    FindingType.SEM_RETRY: (HarnessCategory.RESILIENCIA, _MODEL, True),
    FindingType.SEM_FALLBACK_MODELO: (HarnessCategory.RESILIENCIA, _MODEL, True),
    FindingType.SEM_TRATAMENTO_ERRO: (HarnessCategory.RESILIENCIA, _MODEL, True),
    FindingType.SEM_VALIDACAO_ENTRADA: (HarnessCategory.SAIDAS_VERIFICACAO, _MODEL, True),
    FindingType.GUARDRAIL_INJECAO_AUSENTE: (HarnessCategory.SEGURANCA, _PROMPTS, True),
    FindingType.CONTRADICAO_MODELO_CONFIG: (HarnessCategory.RESILIENCIA, _MODEL, True),
    FindingType.CONTRADICAO_FLUXO_PROMPT: (HarnessCategory.ORQUESTRACAO, _EDGES, True),
}

# Guarda em import: toda a taxonomia tem categoria de harness (nenhum FindingType órfão).
_orphans = set(FindingType) - set(_FINDING_SPEC)
if _orphans:  # pragma: no cover - guarda de desenvolvimento
    raise RuntimeError(f"FindingType sem categoria de harness: {sorted(t.value for t in _orphans)}")

# Confiança (força do sinal estático) por categoria quando avaliada.
_CATEGORY_CONFIDENCE: dict[HarnessCategory, Confidence] = {
    HarnessCategory.ORQUESTRACAO: Confidence.ALTO,
    HarnessCategory.FERRAMENTAS: Confidence.ALTO,
    HarnessCategory.MULTIAGENTE: Confidence.ALTO,
    HarnessCategory.RESILIENCIA: Confidence.ALTO,
    HarnessCategory.SEGURANCA: Confidence.ALTO,
    HarnessCategory.CUSTO_PERFORMANCE: Confidence.ALTO,
    HarnessCategory.AVALIACAO_CONTINUA: Confidence.ALTO,
    HarnessCategory.CONTEXTO: Confidence.MEDIO,
    HarnessCategory.SAIDAS_VERIFICACAO: Confidence.MEDIO,
}

# Categorias sem check nesta fase → nota declarando o vão (roadmap), em vez de fingir avaliação.
_ROADMAP_NOTE: dict[HarnessCategory, str] = {
    HarnessCategory.MEMORIA: "sem check nesta fase — roadmap",
    HarnessCategory.SKILLS: "sem check nesta fase — roadmap",
    HarnessCategory.OBSERVABILIDADE: "sem check nesta fase — roadmap (Tier 2)",
    HarnessCategory.EXECUCAO_DURAVEL: "sem check nesta fase — roadmap (Tier 2)",
    HarnessCategory.CICLO_DE_VIDA: "sem check nesta fase — roadmap (Tier 1)",
}


def _precondition_met(key: str, tsm: TargetStaticModel) -> bool:
    if key == _ALWAYS:
        return True
    if key == _MODEL:
        return bool(tsm.model_assignments) or bool(tsm.agents)
    if key == _TOOLS:
        return bool(tsm.tools)
    if key == _LOOPS:
        return bool(tsm.loops)
    if key == _EDGES:
        return bool(tsm.edges) or bool(tsm.loops)
    if key == _PROMPTS:
        return bool(tsm.prompts)
    return False


def compute_harness_coverage(
    dimensions: list[DimensionResult], tsm: TargetStaticModel
) -> HarnessCoverageReport:
    """Projeta os achados das dimensões nas categorias de harness (Fase 0)."""
    judge_ran = any(dr.judge_opinions for dr in dimensions)
    findings_by_cat: dict[HarnessCategory, list[Finding]] = {cat: [] for cat, _, _ in CATEGORY_META}
    for dr in dimensions:
        for f in dr.findings:
            spec = _FINDING_SPEC.get(f.finding_type)
            if spec is not None:
                findings_by_cat[spec[0]].append(f)

    categories: list[HarnessCategoryCoverage] = []
    total_applicable = total_passed = 0
    for cat, _num, _label in CATEGORY_META:
        cat_fts = [ft for ft, spec in _FINDING_SPEC.items() if spec[0] is cat]
        fired = {f.finding_type for f in findings_by_cat[cat]}
        applicable = {
            ft
            for ft in cat_fts
            if _precondition_met(_FINDING_SPEC[ft][1], tsm) and (_FINDING_SPEC[ft][2] or judge_ran)
        } | (fired & set(cat_fts))

        if cat is HarnessCategory.MULTIAGENTE:
            # Sem FindingType dedicado: avaliada pela classificação de topologia.
            assessed = bool(tsm.agents)
            applicable_n = 1 if assessed else 0
            passed_n = 1 if assessed else 0
            note: str | None = "avaliada pela classificação de topologia" if assessed else None
        else:
            assessed = bool(applicable)
            applicable_n = len(applicable)
            passed_n = len(applicable - fired)
            if assessed:
                note = None
            elif cat is HarnessCategory.CONTEXTO:
                note = "avaliada só com --llm nesta fase"
            elif cat_fts:
                # Tem check, mas o alvo não exercita o componente (ex.: não há ferramentas).
                note = "n/a — alvo não exercita esta categoria"
            else:
                note = _ROADMAP_NOTE.get(cat, "sem check nesta fase — roadmap")

        coverage = round(100 * passed_n / applicable_n) if applicable_n else None
        if assessed:
            total_applicable += applicable_n
            total_passed += passed_n
        categories.append(
            HarnessCategoryCoverage(
                category=cat,
                assessed=assessed,
                coverage=coverage,
                applicable_checks=applicable_n,
                passed_checks=passed_n,
                confidence=_CATEGORY_CONFIDENCE.get(cat, Confidence.BAIXO),
                note=note,
                findings=findings_by_cat[cat],
            )
        )

    overall = round(100 * total_passed / total_applicable) if total_applicable else 0
    assessed_n = sum(1 for c in categories if c.assessed)
    passed_n = sum(1 for c in categories if c.assessed and c.coverage == 100)
    return HarnessCoverageReport(
        coverage=overall,
        assessed_categories=assessed_n,
        passed_categories=passed_n,
        categories=categories,
    )
