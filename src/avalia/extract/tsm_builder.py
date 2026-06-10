"""T-103 — Construtor do TSM (agnóstico de linguagem).

Roteia cada arquivo ao extrator da sua linguagem (registry), mescla os fragmentos e monta um
`TargetStaticModel` imutável + `AnalysisCoverage` + `ReadabilityReport`. Fonte única de fatos
para os avaliadores (leem o mesmo objeto). Nada executa o alvo (RNF-05).

Rastreabilidade: RF-08, RF-12, RF-14; plan §3.1.
"""

from __future__ import annotations

from avalia.domain.contracts import AnalysisCoverage, ReadabilityReport
from avalia.domain.evidence import EvidenceRef
from avalia.domain.tsm import TargetStaticModel
from avalia.extract.base import ExtractionResult
from avalia.extract.registry import get_extractor, language_for_path


def build_tsm(files: dict[str, str]) -> TargetStaticModel:
    """Constrói o TSM a partir do mapa caminho→texto-fonte do alvo."""
    by_lang: dict[str, dict[str, str]] = {}
    best_effort: list[str] = []  # arquivos sem extrator (não analisados a fundo)
    for path, source in files.items():
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

    unreadable_refs = [
        EvidenceRef(file_path=p, symbol="<arquivo>", component_kind="file")
        for p in merged.unreadable_files
    ]
    analyzed = [p for p in merged.files if p not in merged.unreadable_files]
    coverage = AnalysisCoverage(
        fully_analyzed=analyzed,
        sampled=best_effort,
        reason=(
            "arquivos sem extrator dedicado tratados como best-effort" if best_effort else None
        ),
    )
    readability = ReadabilityReport(unreadable_files=unreadable_refs, impacted_dims=[])

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
        coverage=coverage,
        readability=readability,
    )
