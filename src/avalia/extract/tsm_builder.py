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
from avalia.extract.prioritize import rank_files
from avalia.extract.readability import unreadable_files
from avalia.extract.registry import get_extractor, language_for_path

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
)
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
    }
)


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _is_ignorable_path(path: str) -> bool:
    """Documentação/dados não-analisáveis — fora da análise e SEM disparar parcial."""
    base = _basename(path)
    return base in _DOC_BASENAMES or base.endswith(_DOC_EXTENSIONS)


def _is_harness_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    base = p.rsplit("/", 1)[-1]
    return base.startswith("test_") or base.endswith("_test.py") or "/tests/" in p or "/test/" in p


# T4.5 — harness reconhecido por CONFIG de teste / orientação de uso, não só por `test_*`.
_HARNESS_FILES = frozenset({"conftest.py", "tox.ini", "pytest.ini", "noxfile.py"})


def _file_signals_harness(path: str, source: str) -> bool:
    """Sinais de harness em arquivos de config/CI (sinergia com a Frente 1: já parseados)."""
    base = _basename(path)
    p = path.replace("\\", "/").lower()
    if base in _HARNESS_FILES:
        return True
    if base == "pyproject.toml" and ("[tool.pytest" in source or "[tool.tox" in source):
        return True
    if base == "setup.cfg" and ("[tool:pytest]" in source or "[pytest]" in source):
        return True
    if ".github/workflows/" in p and p.endswith((".yml", ".yaml")):
        return "pytest" in source.lower() or "unittest" in source.lower()
    return False


def _detect_harness(files: dict[str, str]) -> bool:
    """RF-DIM-Q1: existe harness de teste/avaliação? Por caminho (`test_*`/`tests/`) OU por
    config de teste (`pyproject [tool.pytest]`, `tox.ini`, `conftest.py`, workflows com pytest)."""
    return any(
        _is_harness_path(path) or _file_signals_harness(path, source)
        for path, source in files.items()
    )


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
    # CB-02: havendo ilegível, todas as dimensões ficam impactadas (postura conservadora Fase 1).
    impacted = list(_ALL_DIMENSIONS) if all_unreadable else []
    readability = ReadabilityReport(unreadable_files=unreadable_refs, impacted_dims=impacted)

    return TargetStaticModel(
        files=list(files),
        agents=merged.agents,
        prompts=merged.prompts,
        tools=merged.tools,
        edges=merged.edges,
        loops=merged.loops,
        model_assignments=merged.model_assignments,
        configs=merged.configs,
        error_handling=merged.error_handling,
        shared_state=merged.shared_state,
        has_harness=_detect_harness(files),
        coverage=coverage,
        readability=readability,
    )
