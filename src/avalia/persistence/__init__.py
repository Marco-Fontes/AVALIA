"""Persistência de laudos históricos (Épico E6) — separada do checkpointer do grafo.

O repositório armazena cada `EvaluationReport` finalizado para comparação entre versões do
mesmo alvo (RF-28/RF-29, D-02). Atrás do Protocol `ReportRepository`: `InMemoryReportRepository`
(dev/testes) e `PostgresReportRepository` (prod). Nada aqui executa o alvo (RNF-05).
"""

from __future__ import annotations

from avalia.persistence.repository import (
    EvaluationReportRecord,
    InMemoryReportRepository,
    ReportRepository,
    make_record,
)

__all__ = [
    "EvaluationReportRecord",
    "InMemoryReportRepository",
    "ReportRepository",
    "make_record",
]
