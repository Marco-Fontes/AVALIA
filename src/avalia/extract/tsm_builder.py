"""T-103 — Construtor do TSM (agnóstico de linguagem) + escala (M5).

Roteia cada arquivo ao extrator da sua linguagem (registry), mescla os fragmentos e monta um
`TargetStaticModel` imutável + `AnalysisCoverage` + `ReadabilityReport`. Fonte única de fatos
para os avaliadores (leem o mesmo objeto). Nada executa o alvo (RNF-05).

M5: antes de extrair, aplica **legibilidade** (T-104 — arquivos ilegíveis fora da análise) e
**priorização/amostragem por sinal** (T-105 — acima de `max_analyzed_files`, só os de maior
sinal são analisados a fundo; o resto é amostrado e declarado em `AnalysisCoverage`).

Rastreabilidade: RF-03, RF-08, RF-12, RF-14; CB-02, CB-05; plan §3.1.
"""

from __future__ import annotations

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import AnalysisCoverage, ReadabilityReport
from avalia.domain.enums import Dimension
from avalia.domain.evidence import EvidenceRef
from avalia.domain.tsm import TargetStaticModel
from avalia.extract.base import ExtractionResult
from avalia.extract.harness import detect_harness
from avalia.extract.prioritize import rank_files
from avalia.extract.readability import unreadable_files
from avalia.extract.registry import get_extractor, language_for_path
from avalia.extract.secrets import redact_config

_ALL_DIMENSIONS = list(Dimension)

# Documentação/dados legitimamente não-analisáveis: NÃO são código/config a inspecionar, logo
# não devem disparar laudo PARCIAL (PLANO-MELHORIAS §3 — "sem amostragem espúria"). Ficam fora
# tanto de `fully_analyzed` quanto de `sampled`. Já a fonte de linguagem não suportada (ex.: .ts)
# permanece em `sampled` (honestidade: código real que não conseguimos ler — TS/JS adiado, #1).
_DOC_EXTENSIONS = (
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".text",
    ".log",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".lock",
    # Build/infra/assets/templates: não são código/config de agentes a avaliar → fora de escopo,
    # não disparam PARCIAL (PLANO-MELHORIAS §3). Antes caíam em `best_effort` e geravam amostragem
    # espúria (ex.: Dockerfile, *.sh, *.css, *.svg num alvo Python/TS).
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".svg",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".bat",
    ".cmd",
    ".mako",
    ".jinja",
    ".jinja2",
    ".j2",
    ".example",
)
_DOC_DIRS = frozenset({"docs", "doc", "documentation"})
_DOCS_DIR_CONFIG_EXTS = (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg")
_DOC_BASENAMES = frozenset(
    {
        "license",
        "license.txt",
        "license.md",
        "copying",
        "authors",
        "notice",
        "codeowners",
        ".gitignore",
        ".gitattributes",
        ".dockerignore",
        ".editorconfig",
        # Lock files (mesmo com extensão de config): dados gerados, não config a avaliar (§10).
        "package-lock.json",
        "poetry.lock",
        "yarn.lock",
        "cargo.lock",
        "composer.lock",
        "pipfile.lock",
        "pnpm-lock.yaml",
        # Marcadores de ferramentas (sem conteúdo a avaliar).
        ".prettierignore",
        ".npmignore",
        ".eslintignore",
        ".stylelintignore",
        ".gitkeep",
        ".keep",
    }
)


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _is_ignorable_path(path: str) -> bool:
    """Documentação/dados não-analisáveis — fora da análise e SEM disparar parcial."""
    base = _basename(path)
    if base in _DOC_BASENAMES or base.endswith(_DOC_EXTENSIONS):
        return True
    if base == "dockerfile" or base.startswith("dockerfile."):
        return True
    # YAML/JSON/TOML/INI sob `docs/` são documentação (specs de API, exemplos), não config
    # operacional a inspecionar — e um arquivo quebrado aí não deve rebaixar a confiança.
    segments = path.replace("\\", "/").lower().split("/")[:-1]
    if any(d in segments for d in _DOC_DIRS) and base.endswith(_DOCS_DIR_CONFIG_EXTS):
        return True
    return False


# CB-02: dimensões cuja confiança depende de ler um arquivo de cada papel. Config alimenta os
# sinais determinísticos de custo/performance/robustez (max_tokens, timeout, fallback); não toca
# as dimensões comportamentais nem a trajetória.
_CONFIG_DEPENDENT_DIMS = frozenset({Dimension.CUSTO, Dimension.PERFORMANCE, Dimension.ROBUSTEZ})


def _dims_impacted_by_unreadable(path: str) -> frozenset[Dimension]:
    """Quais dimensões perdem confiança quando ESTE arquivo é ilegível (CB-02)."""
    lang = language_for_path(path)
    if lang in ("python", "javascript", "typescript"):
        return frozenset(_ALL_DIMENSIONS)  # código: pode conter agentes/prompts/loops/tools
    if lang == "config":
        return _CONFIG_DEPENDENT_DIMS
    return frozenset()  # outro papel → sem dependência dimensional


def build_tsm(files: dict[str, str], config: EvaluatorConfig | None = None) -> TargetStaticModel:
    """Constrói o TSM a partir do mapa caminho→texto-fonte do alvo."""
    # T-104: legibilidade — arquivos ilegíveis saem da análise a fundo (CB-02).
    unreadable_reasons = unreadable_files(files)
    readable = {p: s for p, s in files.items() if p not in unreadable_reasons}

    # T-105: priorização por sinal + amostragem acima do teto de cobertura (RF-12/CB-05).
    limit = config.max_analyzed_files if config else None
    sampled_by_budget: list[str] = []
    if limit is not None and len(readable) > limit:
        ranked = rank_files(readable)
        analyze_paths = ranked[:limit]
        sampled_by_budget = ranked[limit:]
        to_analyze = {p: readable[p] for p in analyze_paths}
    else:
        to_analyze = readable

    by_lang: dict[str, dict[str, str]] = {}
    best_effort: list[str] = []  # fonte sem extrator dedicado (ex.: TS/JS adiado) → amostrada
    ignored_docs: list[str] = []  # documentação/dados não-analisáveis → não dispara parcial
    for path, source in to_analyze.items():
        # Ignoráveis primeiro: docs e LOCK FILES (mesmo com extensão de config, ex.:
        # package-lock.json / pnpm-lock.yaml) saem antes do roteamento ao extrator, senão a
        # extensão de config os capturaria e parsearia como config (ruído — §10).
        if _is_ignorable_path(path):
            ignored_docs.append(path)
            continue
        lang = language_for_path(path)
        if lang and get_extractor(lang):
            by_lang.setdefault(lang, {})[path] = source
        else:
            best_effort.append(path)

    merged = ExtractionResult()
    for lang, lang_files in by_lang.items():
        extractor = get_extractor(lang)
        assert extractor is not None  # garantido pelo filtro acima
        r = extractor.extract(lang_files)
        merged = ExtractionResult(
            files=merged.files + r.files,
            agents=merged.agents + r.agents,
            prompts=merged.prompts + r.prompts,
            tools=merged.tools + r.tools,
            edges=merged.edges + r.edges,
            loops=merged.loops + r.loops,
            model_assignments=merged.model_assignments + r.model_assignments,
            configs=merged.configs + r.configs,
            error_handling=merged.error_handling + r.error_handling,
            shared_state=merged.shared_state + r.shared_state,
            unreadable_files=merged.unreadable_files + r.unreadable_files,
        )

    # Ilegibilidade consolidada: heurística (T-104) + sintaxe inválida no parse (extrator).
    syntax_unreadable = {
        p: "sintaxe inválida ou código ofuscado (falha no parse)" for p in merged.unreadable_files
    }
    all_unreadable = {**syntax_unreadable, **unreadable_reasons}
    unreadable_refs = [
        EvidenceRef(file_path=p, symbol="<arquivo>", component_kind="file", snippet=reason)
        for p, reason in all_unreadable.items()
    ]

    analyzed = [p for p in merged.files if p not in all_unreadable]
    sampled = sampled_by_budget + best_effort
    reasons: list[str] = []
    if sampled_by_budget:
        reasons.append(
            f"{len(sampled_by_budget)} arquivo(s) de menor sinal amostrado(s) por exceder o "
            "teto de cobertura (max_analyzed_files)"
        )
    if best_effort:
        reasons.append("arquivos de linguagem sem extrator dedicado tratados como best-effort")
    if ignored_docs:
        reasons.append(
            f"{len(ignored_docs)} arquivo(s) de documentação/dados não-analisáveis ignorado(s) "
            "(não contam como amostragem — não disparam laudo parcial)"
        )
    coverage = AnalysisCoverage(
        fully_analyzed=analyzed,
        sampled=sampled,
        reason="; ".join(reasons) if reasons else None,
    )
    # CB-02: só as dimensões que DEPENDEM do arquivo ilegível perdem confiança ("marca julgamentos
    # impactados"). Código-fonte ilegível pode conter agentes/prompts/loops/tools → impacto amplo;
    # config ilegível toca apenas sinais de custo/performance/robustez; outro tipo não impacta. Um
    # único arquivo quebrado não colapsa mais TODAS as dimensões para "baixo" (correção do falso
    # "confiança baixa" global que o antigo `_ALL_DIMENSIONS if all_unreadable` produzia).
    impacted_set: set[Dimension] = set()
    for p in all_unreadable:
        impacted_set |= _dims_impacted_by_unreadable(p)
    impacted = [d for d in _ALL_DIMENSIONS if d in impacted_set]
    readability = ReadabilityReport(unreadable_files=unreadable_refs, impacted_dims=impacted)

    return TargetStaticModel(
        files=list(files),
        agents=merged.agents,
        prompts=merged.prompts,
        tools=merged.tools,
        edges=merged.edges,
        loops=merged.loops,
        model_assignments=merged.model_assignments,
        configs=[redact_config(c) for c in merged.configs],  # PR-7: sem segredos no TSM
        error_handling=merged.error_handling,
        shared_state=merged.shared_state,
        has_harness=detect_harness(files),  # T-107: detector único
        coverage=coverage,
        readability=readability,
    )
