"""T-006 — testes do loader de weight_profiles.yaml (RF-16, RNF-06; CA-03, CA-04).

DoD: cada perfil soma 1; neutro = pesos iguais; loader valida cobertura das 7 dimensões.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from avalia.config.weight_profiles import NEUTRAL_PROFILE, load_weight_profiles
from avalia.domain.enums import Dimension
from avalia.domain.weights import WeightSource

pytestmark = pytest.mark.fast


def test_all_shipped_profiles_sum_to_one():
    profiles = load_weight_profiles()
    assert {"rag", "agente_de_acao", "atendimento", "pipeline_dados", NEUTRAL_PROFILE} <= set(
        profiles
    )
    for name, prof in profiles.items():
        assert abs(sum(prof.weights.values()) - 1.0) < 1e-3, name
        assert set(prof.weights) == set(Dimension), name


def test_neutral_is_equal_weights_and_fallback_source():
    neutro = load_weight_profiles()[NEUTRAL_PROFILE]
    assert neutro.source is WeightSource.FALLBACK_NEUTRO
    values = set(neutro.weights.values())
    assert len(values) == 1  # todos iguais


def test_rag_weights_hallucination_above_neutral():
    # CA-03: perfil RAG dá a 'alucinacao' peso maior que o neutro (1/7 ≈ 0.1428)
    profiles = load_weight_profiles()
    assert (
        profiles["rag"].weights[Dimension.ALUCINACAO]
        > profiles[NEUTRAL_PROFILE].weights[Dimension.ALUCINACAO]
    )


def test_profile_not_summing_to_one_is_rejected(tmp_path: Path):
    bad = tmp_path / "wp.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            neutro:
              custo: 0.5
              performance: 0.5
              qualidade: 0.5
              assertividade: 0.5
              alucinacao: 0.5
              trajetoria: 0.5
              robustez: 0.5
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_weight_profiles(bad)


def test_profile_missing_dimension_is_rejected(tmp_path: Path):
    bad = tmp_path / "wp.yaml"
    bad.write_text("neutro:\n  custo: 1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="não cobre"):
        load_weight_profiles(bad)
