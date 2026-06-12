"""T-902 — Esquema do dataset de benchmark + mapeamento score→faixa (MS-04/09; D-03).

O dataset carrega o **rótulo humano de referência** por alvo: topologia/tipo esperados e o
veredito por dimensão (faixa Insuficiente/Adequado/Pronto — semântica de produto, spec §4.2.6).
A CURADORIA do dataset é trabalho humano (D-03), fora de escopo de código; aqui só o contrato e
o loader. `band_of_score` reusa as faixas configuráveis (BandThresholds) para mapear o score de
uma dimensão à faixa comparável ao rótulo. NÃO executa o alvo (RNF-05).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from avalia.config.evaluator_config import BandThresholds
from avalia.domain.enums import Band, Dimension, Topology, Verdict


def band_of_score(score: int, thresholds: BandThresholds | None = None) -> Band:
    """Mapeia score 0–100 → faixa qualitativa (spec §4.2.6). Faixas configuráveis (RNF-06)."""
    t = thresholds or BandThresholds()
    if score >= t.aprovado_min:
        return Band.PRONTO
    if score >= t.aprovacao_condicional_min:
        return Band.ADEQUADO_COM_RESSALVAS
    return Band.INSUFICIENTE


class BenchmarkCase(BaseModel):
    """Rótulo humano de referência para um alvo (MS-04/09)."""

    model_config = ConfigDict(frozen=True)

    target_id: str = Field(min_length=1)
    expected_topology: Topology
    expected_system_type: str | None = None
    # Veredito humano por dimensão (faixa). Só as dimensões rotuladas entram na concordância.
    dimension_labels: dict[Dimension, Band] = Field(default_factory=dict)
    expected_verdict: Verdict | None = None
    notes: str | None = None


class BenchmarkDataset(BaseModel):
    """Conjunto de casos de referência (curadoria = D-03, externa)."""

    model_config = ConfigDict(frozen=True)

    cases: list[BenchmarkCase] = Field(default_factory=list)


def load_dataset(path: str | Path) -> BenchmarkDataset:
    """Carrega o dataset de um arquivo YAML (espelha o loader de weight_profiles)."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return BenchmarkDataset.model_validate(data)
