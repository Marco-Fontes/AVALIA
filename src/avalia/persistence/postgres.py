"""T-601 — `PostgresReportRepository`: schema + CRUD do repositório de laudos.

Reusa o DSN/instância do PostgresSaver (resolução #3). psycopg é importado de forma PREGUIÇOSA
(só ao instanciar/usar) para que o módulo possa ser importado sem o driver. Schema idempotente
(`CREATE TABLE IF NOT EXISTS`) — nenhuma operação destrutiva. Nada executa o alvo (RNF-05).

Rastreabilidade: RF-28, RF-29, D-02; resolução #3.
"""

from __future__ import annotations

from typing import Any

from avalia.domain.contracts import EvaluationReport
from avalia.persistence.repository import EvaluationReportRecord

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS avalia_reports (
        report_id      text PRIMARY KEY,
        target_id      text NOT NULL,
        target_version text NOT NULL,
        created_at     timestamptz NOT NULL,
        verdict        text NOT NULL,
        score          integer NOT NULL,
        report_json    jsonb NOT NULL,
        findings_index jsonb NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_avalia_reports_target "
    "ON avalia_reports (target_id, created_at DESC)",
)

_COLUMNS = (
    "report_id, target_id, target_version, created_at, verdict, score, report_json, findings_index"
)


class PostgresReportRepository:
    """Backend Postgres do repositório de laudos (RF-28)."""

    def __init__(self, dsn: str, *, ensure_schema: bool = True) -> None:
        import psycopg  # import preguiçoso: o módulo importa sem o driver instalado

        self._psycopg = psycopg
        self._dsn = dsn
        if ensure_schema:
            with psycopg.connect(dsn) as conn:
                for statement in _DDL:
                    conn.execute(statement)
                conn.commit()

    def save(self, record: EvaluationReportRecord) -> None:
        from psycopg.types.json import Jsonb

        with self._psycopg.connect(self._dsn) as conn:
            conn.execute(
                f"INSERT INTO avalia_reports ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record.report_id,
                    record.target_id,
                    record.target_version,
                    record.created_at,
                    record.verdict,
                    record.score,
                    Jsonb(record.report.model_dump(mode="json")),
                    Jsonb(record.findings_index),
                ),
            )
            conn.commit()

    def latest_for(self, target_id: str) -> EvaluationReportRecord | None:
        with self._psycopg.connect(self._dsn) as conn:
            row: Any = conn.execute(
                f"SELECT {_COLUMNS} FROM avalia_reports WHERE target_id = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (target_id,),
            ).fetchone()
        if row is None:
            return None
        return EvaluationReportRecord(
            report_id=row[0],
            target_id=row[1],
            target_version=row[2],
            created_at=row[3],
            verdict=row[4],
            score=row[5],
            report=EvaluationReport.model_validate(row[6]),
            findings_index=list(row[7]),
        )
