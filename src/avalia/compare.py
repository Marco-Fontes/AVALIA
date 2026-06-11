"""N6 `compare_history` (T-605) — deltas, regressões/melhorias e diff de achados.

Compara o laudo atual com o anterior do mesmo alvo: deltas por dimensão aplicável, regressões
(delta < 0) e melhorias (delta > 0), e classifica os achados em resolvido/persistente/novo por
**identidade estável** (RF-29) — robusto a reformulação e a código que muda de lugar.

Rastreabilidade: RF-28, RF-29; CA-15; plan §3.8b.
"""

from __future__ import annotations

from avalia.domain.contracts import DimensionResult, VersionComparison
from avalia.domain.enums import Dimension
from avalia.persistence.repository import EvaluationReportRecord

_DIM_ORDER = {d: i for i, d in enumerate(Dimension)}


def _scores(results: list[DimensionResult]) -> dict[Dimension, int]:
    return {dr.dimension: dr.score for dr in results if dr.applicable and dr.score is not None}


def compare(
    current_results: list[DimensionResult],
    current_findings_index: list[str],
    prev: EvaluationReportRecord,
) -> VersionComparison:
    cur = _scores(current_results)
    old = _scores(list(prev.report.dimensions))
    common = sorted((d for d in cur if d in old), key=lambda d: _DIM_ORDER[d])
    deltas = {d: cur[d] - old[d] for d in common}

    regressions = [f"{d.value}: {deltas[d]}" for d in common if deltas[d] < 0]
    improvements = [f"{d.value}: +{deltas[d]}" for d in common if deltas[d] > 0]

    cur_ids = set(current_findings_index)
    prev_ids = set(prev.findings_index)
    return VersionComparison(
        prev_report_id=prev.report_id,
        deltas=deltas,
        regressions=regressions,
        improvements=improvements,
        resolved_findings=sorted(prev_ids - cur_ids),
        persistent_findings=sorted(prev_ids & cur_ids),
        new_findings=sorted(cur_ids - prev_ids),
    )
