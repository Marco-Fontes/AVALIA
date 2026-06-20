"""M8-2 — `JsonFileReportRepository`: backend local de laudos em arquivos JSON (sem dependências).

Backend de persistência single-user para a porta de uso (CLI), preservando a baixa fricção
(RNF-11): grava cada `EvaluationReportRecord` como um JSON em `<base_dir>/<report_id>.json` e
implementa o mesmo `Protocol ReportRepository` (RF-28) dos backends InMemory/Postgres.

Decisão de path: o nome do arquivo é o `report_id` (uuid hex) — cross-platform e estável. O
`target_id` (livre, fornecido pelo usuário — S-02) vive só DENTRO do JSON, **nunca no caminho**,
evitando sanitização de caracteres inválidos por sistema de arquivos (`:`/`/` etc.).

Nada executa o alvo (RNF-05). Rastreabilidade: RF-28, RF-29, D-02; RNF-11.
"""

from __future__ import annotations

from pathlib import Path

from avalia.persistence.repository import EvaluationReportRecord


class JsonFileReportRepository:
    """Repositório de laudos em arquivos JSON (dev/single-user). Implementa `ReportRepository`."""

    def __init__(self, base_dir: str | Path) -> None:
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: EvaluationReportRecord) -> None:
        path = self._dir / f"{record.report_id}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def latest_for(self, target_id: str) -> EvaluationReportRecord | None:
        """Laudo mais recente (por `created_at`) do `target_id`, ou `None` se não houver."""
        latest: EvaluationReportRecord | None = None
        for path in self._dir.glob("*.json"):
            try:
                record = EvaluationReportRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue  # arquivo corrompido/alheio → ignora, nunca quebra (postura defensiva)
            if record.target_id != target_id:
                continue
            if latest is None or record.created_at > latest.created_at:
                latest = record
        return latest
