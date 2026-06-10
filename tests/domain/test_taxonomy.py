"""T-003 — testes da taxonomia controlada e da identidade estável de achado.

DoD: todo FindingType tem dimensão dona; util de normalização testado; chave composta
(dimensão, FindingType, localização_normalizada) → hash ESTÁVEL (resolução #3, RF-29, RNF-01).
"""

from __future__ import annotations

import pytest

from avalia.domain.enums import Dimension
from avalia.domain.taxonomy import (
    FINDING_TYPE_DIMENSION,
    FindingType,
    dimension_of,
    finding_identity,
    normalize_location,
)

pytestmark = pytest.mark.fast


def test_every_finding_type_has_owner_dimension():
    assert set(FINDING_TYPE_DIMENSION) == set(FindingType)
    for ft in FindingType:
        assert isinstance(dimension_of(ft), Dimension)


def test_loop_sem_teto_belongs_to_trajetoria():
    assert dimension_of(FindingType.LOOP_SEM_TETO) is Dimension.TRAJETORIA


def test_sem_fallback_modelo_belongs_to_robustez():
    # RNF-12 / resolução v1.3 — fallback de modelo do ALVO é achado de Robustez.
    assert dimension_of(FindingType.SEM_FALLBACK_MODELO) is Dimension.ROBUSTEZ


def test_normalize_location_ignores_path_separators_and_whitespace():
    a = normalize_location("pkg\\mod.py", "  run_agent ")
    b = normalize_location("pkg/mod.py", "run_agent")
    assert a == b == "pkg/mod.py::run_agent"


def test_identity_is_stable_and_line_independent():
    # mesma (dim, tipo, símbolo) em locais textualmente diferentes mas equivalentes → mesmo id
    loc1 = normalize_location("pkg/mod.py", "loop_principal")
    loc2 = normalize_location("pkg\\mod.py", "loop_principal")
    id1 = finding_identity(Dimension.TRAJETORIA, FindingType.LOOP_SEM_TETO, loc1)
    id2 = finding_identity(Dimension.TRAJETORIA, FindingType.LOOP_SEM_TETO, loc2)
    assert id1 == id2
    assert len(id1) == 64  # sha-256 hex


def test_identity_differs_on_different_finding_type():
    loc = normalize_location("pkg/mod.py", "loop_principal")
    id_loop = finding_identity(Dimension.TRAJETORIA, FindingType.LOOP_SEM_TETO, loc)
    id_dead = finding_identity(Dimension.TRAJETORIA, FindingType.CAMINHO_MORTO, loc)
    assert id_loop != id_dead
