"""Meta-avaliação do AVALIA (M6/E9): valida se o AVALIA julga bem (MS-04/07/08/09).

Job OFFLINE sobre laudos + dataset de referência humano — não altera o grafo (plan §3.11). Mede
concordância de veredito por dimensão (métrica primária, EC-10), concordância de classificação e
calibração de confiança. NÃO fixa limiar de "confiável" (D-04) nem curou dataset (D-03).
"""

from __future__ import annotations

from avalia.metaeval.dataset import (
    BenchmarkCase,
    BenchmarkDataset,
    band_of_score,
    load_dataset,
)
from avalia.metaeval.harness import (
    CaseResult,
    MetaEvalReport,
    evaluate_dataset,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkDataset",
    "CaseResult",
    "MetaEvalReport",
    "band_of_score",
    "evaluate_dataset",
    "load_dataset",
]
