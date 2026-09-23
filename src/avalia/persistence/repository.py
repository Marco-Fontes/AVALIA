"""T-601/T-603/T-604 — `EvaluationReportRecord`, Protocol e repositório em memória.

`EvaluationReportRecord` é o modelo de dados do repositório (T-601). `make_record` deriva o
`findings_index` (identidades estáveis de todos os achados — T-604), reusando `Finding.identity`
(M0). `InMemoryReportRepository` é o backend de dev/testes; o Postgres vive em `postgres.py`.

Rastreabilidade: RF-28, RF-29, D-02; resolução #3.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from avalia.domain.contracts import EvaluationReport
from avalia.domain.submission import TargetMetadata


class EvaluationReportRecord(BaseModel):
    """Registro persistido de um laudo finalizado (T-601)."""

    model_config = ConfigDict(frozen=True)

    report_id: str
    target_id: str
    target_version: str
    created_at: datetime
    verdict: str
    score: int
    report: EvaluationReport
    findings_index: list[str] = Field(default_factory=list)


def findings_index_of(report: EvaluationReport) -> list[str]:
    """Identidades estáveis de todos os achados do laudo (T-604), ordenadas."""
    return sorted({f.identity for dr in report.dimensions for f in dr.findings})


_CLOCK_LOCK = threading.Lock()
_last_created_at: datetime | None = None


def _next_created_at() -> datetime:
    """`created_at` ESTRITAMENTE crescente no processo. O relógio de parede pode ter resolução
    grossa (15,6 ms no Windows): dois laudos gravados em sequência ganhavam o mesmo instante e
    `latest_for` desempatava arbitrariamente (RF-29 comparava com a versão errada)."""
    global _last_created_at
    with _CLOCK_LOCK:
        now = datetime.now(UTC)
        if _last_created_at is not None and now <= _last_created_at:
            now = _last_created_at + timedelta(microseconds=1)
        _last_created_at = now
        return now


def make_record(report: EvaluationReport, metadata: TargetMetadata) -> EvaluationReportRecord:
    """Monta o registro a partir do laudo + metadados do alvo (S-02)."""
    return EvaluationReportRecord(
        report_id=uuid4().hex,
        target_id=metadata.target_id,
        target_version=metadata.version,
        created_at=_next_created_at(),
        verdict=report.header.verdict.value,
        score=report.header.score,
        report=report,
        findings_index=findings_index_of(report),
    )


class ReportRepository(Protocol):
    """Porta de persistência de laudos (RF-28). Backends: InMemory (dev), Postgres (prod)."""

    def save(self, record: EvaluationReportRecord) -> None: ...

    def latest_for(self, target_id: str) -> EvaluationReportRecord | None: ...


class InMemoryReportRepository:
    """Backend em memória (dev/testes). Mantém ordem de inserção por `target_id`."""

    def __init__(self) -> None:
        self._by_target: dict[str, list[EvaluationReportRecord]] = {}

    def save(self, record: EvaluationReportRecord) -> None:
        self._by_target.setdefault(record.target_id, []).append(record)

    def latest_for(self, target_id: str) -> EvaluationReportRecord | None:
        history = self._by_target.get(target_id)
        return history[-1] if history else None
