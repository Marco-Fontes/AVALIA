"""T-106 — Contradições config↔código (CB-08, RNF-08).

Cada contradição é um `Finding` na dimensão dona (regra 4), com evidência dos dois lados.
Nada é executado/importado (RNF-05).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.domain.enums import Dimension
from avalia.domain.taxonomy import FindingType
from avalia.extract.contradictions import detect_contradictions
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

_FIX = Path(__file__).resolve().parents[1] / "fixtures" / "contradicao_config_codigo"


def _tsm():
    files = {f.name: f.read_text(encoding="utf-8") for f in _FIX.glob("*.py")}
    return build_tsm(files)


def test_model_contradiction_is_custo_finding_with_two_sided_evidence():
    findings = [
        f
        for f in detect_contradictions(_tsm())
        if f.finding_type is FindingType.CONTRADICAO_MODELO_CONFIG
    ]
    assert findings, "esperava contradição de modelo declarado≠usado"
    f = findings[0]
    assert f.dimension is Dimension.CUSTO  # dimensão dona (regra 4)
    assert len(f.evidence) == 2  # ambos os lados (código e config) — RNF-07


def test_flow_contradiction_is_trajetoria_finding():
    findings = [
        f
        for f in detect_contradictions(_tsm())
        if f.finding_type is FindingType.CONTRADICAO_FLUXO_PROMPT
    ]
    assert findings, "esperava contradição prompt↔fluxo"
    assert findings[0].dimension is Dimension.TRAJETORIA
    assert "verificador" in findings[0].statement


def test_no_false_positive_on_consistent_artifact():
    files = {
        "ok.py": (
            "MODEL_NAME = 'claude-opus'\n"
            "def answerer(state):\n    return chat(model=MODEL_NAME)\n"
            "def build(g):\n    g.add_edge('planner', 'answerer')\n"
        )
    }
    # modelo usado referencia a config (coerente) e não há prompt de roteamento → sem contradição.
    assert detect_contradictions(build_tsm(files)) == []


def test_contradiction_surfaces_in_dimension_results():
    from avalia.evaluators.custo import evaluate_custo
    from avalia.evaluators.trajetoria import evaluate_trajetoria

    tsm = _tsm()
    custo = evaluate_custo(tsm)
    traj = evaluate_trajetoria(tsm)
    assert any(f.finding_type is FindingType.CONTRADICAO_MODELO_CONFIG for f in custo.findings)
    assert any(f.finding_type is FindingType.CONTRADICAO_FLUXO_PROMPT for f in traj.findings)
    # CB-08: contradição reduz a confiança das dimensões afetadas.
    assert custo.confidence_reason and "CB-08" in custo.confidence_reason
