"""T-303..T-307/T-309 — testes unitários determinísticos dos 6 avaliadores de dimensão.

Cobre findings de ausência, confiança baixa sem harness (CA-06), `static_limitations` nas
comportamentais (CA-07/RF-13) e inaplicabilidade da Trajetória em agente único (CA-08).
"""

from __future__ import annotations

import pytest

from avalia.classify import classify_target
from avalia.domain.enums import BEHAVIORAL_DIMENSIONS, Confidence, Dimension
from avalia.domain.taxonomy import FindingType, dimension_of
from avalia.evaluators.alucinacao import evaluate_alucinacao
from avalia.evaluators.assertividade import evaluate_assertividade
from avalia.evaluators.custo import evaluate_custo
from avalia.evaluators.performance import evaluate_performance
from avalia.evaluators.qualidade import evaluate_qualidade
from avalia.evaluators.robustez import evaluate_robustez
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

# Alvo "pobre": sem timeout/retry/cache/validação/citação/escalonamento/harness.
_BARE = 'PROMPT = "Você é um assistente."\n\n\ndef agent(state):\n    return call(model=m)\n'


def _ftypes(dr):
    return {f.finding_type for f in dr.findings}


def test_custo_flags_token_and_cache_only_own_dimension():
    dr = evaluate_custo(build_tsm({"main.py": _BARE}))
    assert FindingType.SEM_LIMITE_TOKENS in _ftypes(dr)
    assert FindingType.SEM_CACHE in _ftypes(dr)
    # nenhum achado de outra dimensão (regra 4)
    assert all(dimension_of(f.finding_type) is Dimension.CUSTO for f in dr.findings)


def test_performance_flags_timeout():
    dr = evaluate_performance(build_tsm({"main.py": _BARE}))
    assert FindingType.SEM_TIMEOUT in _ftypes(dr)
    assert dr.confidence is Confidence.ALTO  # P2 determinístico


def test_qualidade_no_harness_low_confidence():
    # CA-06: sem harness → confiança baixa + justificativa
    dr = evaluate_qualidade(build_tsm({"main.py": _BARE}))
    assert FindingType.SEM_HARNESS_VERIFICACAO in _ftypes(dr)
    assert dr.confidence is Confidence.BAIXO
    assert dr.confidence_reason and "harness" in dr.confidence_reason.lower()
    assert dr.static_limitations  # comportamental (RF-13)


def test_qualidade_with_harness_not_low():
    dr = evaluate_qualidade(
        build_tsm({"main.py": _BARE, "tests/test_x.py": "def test_a():\n    pass\n"})
    )
    assert dr.confidence is not Confidence.BAIXO
    assert FindingType.SEM_HARNESS_VERIFICACAO not in _ftypes(dr)


def test_assertividade_flags_escalation_and_declares_limit():
    dr = evaluate_assertividade(build_tsm({"main.py": _BARE}))
    assert FindingType.SEM_ESCALONAMENTO_BAIXA_CONFIANCA in _ftypes(dr)
    assert dr.static_limitations


def test_alucinacao_flags_citation_and_declares_phase1_limit():
    # CA-07: declara que a taxa real não é medível na Fase 1
    dr = evaluate_alucinacao(build_tsm({"main.py": _BARE}))
    assert FindingType.PROMPT_SEM_CITACAO in _ftypes(dr)
    assert "não" in dr.static_limitations.lower() and "fase 2" in dr.static_limitations.lower()


def test_robustez_flags_retry_fallback_error_validation():
    dr = evaluate_robustez(build_tsm({"main.py": _BARE}))
    expected = {
        FindingType.SEM_RETRY,
        FindingType.SEM_FALLBACK_MODELO,
        FindingType.SEM_TRATAMENTO_ERRO,
        FindingType.SEM_VALIDACAO_ENTRADA,
        FindingType.GUARDRAIL_INJECAO_AUSENTE,
    }
    assert expected <= _ftypes(dr)
    assert all(dimension_of(f.finding_type) is Dimension.ROBUSTEZ for f in dr.findings)


def test_behavioral_dims_require_static_limitations():
    tsm = build_tsm({"main.py": _BARE})
    for evaluator in (evaluate_qualidade, evaluate_assertividade, evaluate_alucinacao):
        dr = evaluator(tsm)
        assert dr.dimension in BEHAVIORAL_DIMENSIONS
        assert dr.static_limitations


def test_trajetoria_inapplicable_for_single_agent():
    # CA-08: agente único sem grafo/loops/ferramentas → Trajetória não aplicável
    tsm = build_tsm({"main.py": 'PROMPT = "único"\n'})
    classification = classify_target(tsm)
    dr = evaluate_trajetoria(tsm, classification)
    assert dr.applicable is False
    assert dr.score is None
    assert dr.reasoning  # razão declarada
