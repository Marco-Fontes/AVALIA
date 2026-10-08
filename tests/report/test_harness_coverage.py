"""Fase 0 — camada de cobertura de harness (projeção sobre as dimensões).

DoD: todo FindingType tem categoria; achado rebaixa a categoria e a cobertura geral; categorias
sem check nesta fase aparecem como n/a declarada (fora do denominador). Nada executa o alvo.
"""

from __future__ import annotations

import pytest

from avalia.domain.enums import HarnessCategory
from avalia.domain.taxonomy import FindingType
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm
from avalia.report.harness import _FINDING_SPEC, compute_harness_coverage

pytestmark = pytest.mark.fast

_LOOP_SEM_TETO = """
def solver_agent(state):
    while True:
        state = step(state)


def step(state):
    return state
"""


def _cov(src: str):
    tsm = build_tsm({"main.py": src})
    return compute_harness_coverage([evaluate_trajetoria(tsm)], tsm), tsm


def test_every_findingtype_has_a_harness_category():
    assert set(FindingType) == set(_FINDING_SPEC)


def test_uncapped_loop_lowers_orquestracao_and_overall():
    hc, _ = _cov(_LOOP_SEM_TETO)
    orq = next(c for c in hc.categories if c.category is HarnessCategory.ORQUESTRACAO)
    assert orq.assessed
    assert any(f.finding_type is FindingType.LOOP_SEM_TETO for f in orq.findings)
    assert orq.coverage is not None and orq.coverage < 100
    assert hc.coverage < 100  # o achado puxa a cobertura geral para baixo


def test_categories_without_checks_are_declared_na_not_zero():
    hc, _ = _cov(_LOOP_SEM_TETO)
    for cat in (
        HarnessCategory.MEMORIA,
        HarnessCategory.SKILLS,
        HarnessCategory.OBSERVABILIDADE,
        HarnessCategory.EXECUCAO_DURAVEL,
        HarnessCategory.CICLO_DE_VIDA,
    ):
        c = next(x for x in hc.categories if x.category is cat)
        assert c.assessed is False
        assert c.coverage is None  # n/a, não zero — fora do denominador
        assert c.note  # vão declarado (roadmap)


def test_coverage_is_a_true_0_100_with_no_ceiling():
    # Categoria sem achado e avaliável chega a 100% (sem teto artificial de 90).
    tsm = build_tsm({"main.py": "def f():\n    for i in range(3):\n        print(i)\n"})
    hc = compute_harness_coverage([evaluate_trajetoria(tsm)], tsm)
    orq = next(c for c in hc.categories if c.category is HarnessCategory.ORQUESTRACAO)
    assert orq.assessed and orq.coverage == 100
