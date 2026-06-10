"""T-002 — `EvidenceRef`: evidência rastreável (arquivo + SÍMBOLO).

Decisão #3 / regra inviolável 5: evidência = arquivo + símbolo/nó. A LINHA é evidência,
NÃO identidade — por isso `symbol` é obrigatório e as linhas são opcionais. A identidade
estável de achado vive em taxonomy.normalize_location / finding_identity (T-003).

Rastreabilidade: RF-14, RNF-07; resolução #3.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceRef(BaseModel):
    """Aponta para um elemento do artefato do ALVO. Construída por leitura estática (TSM)."""

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(min_length=1)
    symbol: str = Field(
        min_length=1,
        description="Símbolo/nó (função/classe/nó do grafo). Obrigatório — linha não basta.",
    )
    component_kind: str = Field(
        min_length=1,
        description="Tipo do elemento: agent, prompt, tool, edge, loop, model_assignment, config…",
    )
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    snippet: str | None = None

    @field_validator("symbol")
    @classmethod
    def _symbol_not_blank(cls, v: str) -> str:
        # Reforça a regra: símbolo em branco equivale a "só linha" → proibido.
        if not v.strip():
            raise ValueError("EvidenceRef.symbol não pode ser vazio (evidência exige símbolo).")
        return v
