"""N0 `ingest_validate` (T-201) — recepção, inventário e validação de obrigatórios.

Monta `ComponentInventory` cobrindo os seis componentes do pacote (spec §4.1): código-fonte,
prompts, configuração, harness, instrumentação e metadados. Apenas o **código-fonte** bloqueia
a avaliação — sem ele → `status=error` com mensagem que cita o componente, **sem gerar laudo**
(RF-02/CA-01). A ausência de componentes OPCIONAIS (harness, instrumentação) é registrada no
inventário e computada negativamente nas dimensões afetadas (CB-01); não bloqueia.

A detecção dos componentes opcionais é heurística e declarada (RNF-08) — feita sobre o TEXTO dos
artefatos, sem nunca importar/executar o alvo (RNF-05/S-04). A `EvaluatorConfig` já é validada na
construção (CB-07, T-005).

Rastreabilidade: RF-01, RF-02, CB-07; CA-01, CB-01.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from avalia.domain.contracts import ComponentInventory
from avalia.domain.enums import RunStatus
from avalia.domain.submission import Submission

# Sinais (heurísticos, declarados) de componentes opcionais/obrigatórios no texto dos artefatos.
_HARNESS_PATH_HINTS = ("test_", "_test.py", "/tests/", "/test/", "conftest")
_INSTRUMENTATION_HINTS = (
    "logging",
    "logger",
    "opentelemetry",
    "prometheus",
    "structlog",
    "langsmith",
    "logfire",
    "tracing",
    "metrics",
)
_PROMPT_HINTS = ("prompt", "system_prompt", "instruction", "persona", "systemmessage")
_CONFIG_PATH_HINTS = ("config", "settings", ".env", ".yaml", ".yml", ".toml", ".ini")
_CONFIG_CONTENT_HINTS = ("os.environ", "getenv", "dotenv", "pydantic_settings", "basesettings")


class IngestOutcome(BaseModel):
    """Resultado de N0: inventário + status (+ mensagem se erro)."""

    model_config = ConfigDict(frozen=True)

    inventory: ComponentInventory
    status: RunStatus
    error_message: str | None = None


def _any_path(files: dict[str, str], hints: tuple[str, ...]) -> bool:
    return any(any(h in p.replace("\\", "/").lower() for h in hints) for p in files)


def _any_content(files: dict[str, str], hints: tuple[str, ...]) -> bool:
    return any(any(h in src.lower() for h in hints) for src in files.values())


def _detect_components(files: dict[str, str]) -> tuple[list[str], list[str]]:
    """Presentes/ausentes entre os componentes opcionais e obrigatórios não-código (heurístico)."""
    checks = {
        "prompts": _any_content(files, _PROMPT_HINTS),
        "configuracao": _any_path(files, _CONFIG_PATH_HINTS)
        or _any_content(files, _CONFIG_CONTENT_HINTS),
        "harness": _any_path(files, _HARNESS_PATH_HINTS),
        "instrumentacao": _any_content(files, _INSTRUMENTATION_HINTS),
    }
    present = [name for name, ok in checks.items() if ok]
    missing = [name for name, ok in checks.items() if not ok]
    return present, missing


def ingest_validate(submission: Submission) -> IngestOutcome:
    files = submission.artifact_files
    present: list[str] = []
    missing: list[str] = []

    has_source = bool(submission.python_files())
    (present if has_source else missing).append("codigo_fonte")

    # Componentes não-bloqueantes (opcionais/secundários) — registrados para auditoria (RF-01).
    opt_present, opt_missing = _detect_components(files)
    present.extend(opt_present)
    missing.extend(opt_missing)

    present.append("metadados")  # sempre presente em Submission (S-02)

    inventory = ComponentInventory(present=present, missing=missing)

    if not has_source:
        return IngestOutcome(
            inventory=inventory,
            status=RunStatus.ERROR,
            error_message=(
                "Componente obrigatório ausente: código-fonte. A avaliação não prossegue "
                "e nenhum laudo é gerado (RF-02/CA-01)."
            ),
        )
    return IngestOutcome(inventory=inventory, status=RunStatus.OK)
