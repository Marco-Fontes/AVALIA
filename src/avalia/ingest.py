"""N0 `ingest_validate` (T-201) — recepção, inventário e validação de obrigatórios.

Monta `ComponentInventory`, valida componentes obrigatórios. Sem código-fonte → `status=error`
com mensagem que cita o componente, **sem gerar laudo** (RF-02/CA-01). A `EvaluatorConfig` já
é validada na construção (CB-07, T-005).

Rastreabilidade: RF-01, RF-02, CB-07; CA-01.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from avalia.domain.contracts import ComponentInventory
from avalia.domain.enums import RunStatus
from avalia.domain.submission import Submission


class IngestOutcome(BaseModel):
    """Resultado de N0: inventário + status (+ mensagem se erro)."""

    model_config = ConfigDict(frozen=True)

    inventory: ComponentInventory
    status: RunStatus
    error_message: str | None = None


def ingest_validate(submission: Submission) -> IngestOutcome:
    present: list[str] = []
    missing: list[str] = []

    if submission.python_files():
        present.append("codigo_fonte")
    else:
        missing.append("codigo_fonte")
    present.append("metadados")  # sempre presente em Submission (S-02)

    inventory = ComponentInventory(present=present, missing=missing)

    if "codigo_fonte" in missing:
        return IngestOutcome(
            inventory=inventory,
            status=RunStatus.ERROR,
            error_message=(
                "Componente obrigatório ausente: código-fonte. A avaliação não prossegue "
                "e nenhum laudo é gerado (RF-02/CA-01)."
            ),
        )
    return IngestOutcome(inventory=inventory, status=RunStatus.OK)
