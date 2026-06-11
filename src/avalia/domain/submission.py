"""Contrato de entrada `Submission` (plan §4.1) — entrada de N0 `ingest_validate`.

O artefato do ALVO é fornecido como TEXTO-FONTE (mapa caminho→conteúdo). É DADO inerte:
nunca importado, instanciado ou executado (RNF-05/S-04) — apenas lido por `ast`. A identidade
do alvo (`target_id`, versão) vem dos metadados do usuário (S-02), não é inferida do código.

Rastreabilidade: RF-01, S-02; plan §4.1.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from avalia.config.evaluator_config import EvaluatorConfig


class TargetMetadata(BaseModel):
    """Identidade declarada do alvo (fornecida pelo usuário — S-02)."""

    model_config = ConfigDict(frozen=True)

    target_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str | None = None


class Submission(BaseModel):
    """Pacote submetido ao AVALIA: artefato (texto), metadados e config do avaliador."""

    model_config = ConfigDict(frozen=True)

    # caminho relativo → conteúdo-fonte (texto). Vazio = sem código-fonte (CA-01).
    artifact_files: dict[str, str] = Field(default_factory=dict)
    metadata: TargetMetadata
    config: EvaluatorConfig = Field(default_factory=EvaluatorConfig)

    def python_files(self) -> dict[str, str]:
        """Subconjunto de arquivos Python (por extensão) — entrada do extrator."""
        return {p: src for p, src in self.artifact_files.items() if p.endswith(".py")}
