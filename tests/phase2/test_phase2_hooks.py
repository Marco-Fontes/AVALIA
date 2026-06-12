"""T-804 — Ganchos da Fase 2: declarados, vazios e NÃO referenciados no caminho da Fase 1.

Garante que nada da Fase 2 é cabeado ao grafo atual e que nada executa o alvo (RNF-05/S-04).
"""

from __future__ import annotations

import pytest

from avalia.phase2 import TargetRunner, TestCaseGenerator, execution_gate

pytestmark = pytest.mark.fast


def test_hooks_are_declared_but_empty():
    assert isinstance(TargetRunner, type)  # Protocol declarado
    assert isinstance(TestCaseGenerator, type)
    # execution_gate é no-op da Fase 1: invocá-lo é explicitamente não suportado.
    with pytest.raises(NotImplementedError):
        execution_gate({})


def test_phase1_graph_does_not_reference_phase2_hooks():
    import avalia.graph.build_graph as bg
    import avalia.graph.nodes as nodes

    src = bg.__file__
    for module in (bg, nodes):
        text = open(module.__file__, encoding="utf-8").read()
        assert "phase2" not in text, f"{module.__name__} referencia phase2 (proibido na Fase 1)"
        assert "execution_gate" not in text
        assert "TargetRunner" not in text
    assert src  # sanity


def test_dynamic_metrics_remains_opaque_none_in_phase1():
    # O slot da Fase 2 permanece None na Fase 1 (S-05) — rejeita valor concreto.
    from pydantic import ValidationError

    from avalia.domain.contracts import DimensionResult
    from avalia.domain.enums import Confidence, Dimension

    with pytest.raises(ValidationError):
        DimensionResult(
            dimension=Dimension.CUSTO,
            applicable=True,
            score=80,
            confidence=Confidence.ALTO,
            reasoning="ok",
            dynamic_metrics={"latency_ms": 10},  # Fase 2 — proibido na Fase 1
        )
