"""T-301/T-308 — testes do framework de check e do avaliador de Trajetória.

DoD: hash determinístico bit-idêntico entre execuções (RNF-01/CA-14); loop sem teto vira
LOOP_SEM_TETO com evidência (símbolo) e score na faixa 50–74 (suporta CA-09).
"""

from __future__ import annotations

import pytest

from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.taxonomy import FindingType
from avalia.evaluators.checks import deterministic_hash, deterministic_outcome
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

_LOOP_SEM_TETO = """
def solver_agent(state):
    while True:
        state = step(state)


def step(state):
    return state
"""

_LOOP_OK = """
def worker():
    total = 0
    for i in range(5):
        total += i
    return total
"""


def test_deterministic_hash_is_stable():
    a = deterministic_hash("c1", [["x", True], ["y", False]])
    b = deterministic_hash("c1", [["x", True], ["y", False]])
    assert a == b and len(a) == 64


def test_deterministic_outcome_carries_hash():
    out = deterministic_outcome("T3_loop_cap", passed=False, facts=[["n", False]])
    assert out.deterministic_hash and out.nature.value == "deterministico"


def test_trajetoria_flags_uncapped_loop_in_band():
    tsm = build_tsm({"main.py": _LOOP_SEM_TETO})
    dr = evaluate_trajetoria(tsm)
    assert dr.dimension is Dimension.TRAJETORIA
    assert 50 <= dr.score <= 74  # faixa de aprovação condicional (CA-09)
    loop_findings = [f for f in dr.findings if f.finding_type is FindingType.LOOP_SEM_TETO]
    assert len(loop_findings) == 1
    assert loop_findings[0].urgency is Urgency.CRITICO
    assert loop_findings[0].evidence[0].symbol.startswith("solver_agent")
    # recomendação rastreável ao achado (CA-09)
    rec = dr.recommendations[0]
    assert "teto de iteração" in rec.statement
    assert rec.traces_to == loop_findings[0].identity


def test_trajetoria_clean_target_scores_high():
    tsm = build_tsm({"main.py": _LOOP_OK})
    dr = evaluate_trajetoria(tsm)
    assert dr.score >= 75
    assert not [f for f in dr.findings if f.finding_type is FindingType.LOOP_SEM_TETO]
    assert dr.reasoning  # CA-05: reasoning sempre presente
    assert dr.confidence is Confidence.ALTO
