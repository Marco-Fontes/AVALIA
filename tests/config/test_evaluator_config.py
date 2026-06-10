"""T-005 — testes de EvaluatorConfig (RNF-06, RNF-12, CB-07, RF-18).

DoD: pesos inválidos → erro ANTES da análise (CB-07); limiares/modelo/fallback/back-end de
config, nunca constantes; trocar provedor/modelo é só configuração.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from avalia.config.evaluator_config import (
    Backend,
    BandThresholds,
    EvaluatorConfig,
    ModelRef,
    NodeModelConfig,
)
from avalia.domain.enums import Dimension, Verdict

pytestmark = pytest.mark.fast


def test_defaults_are_50_75_and_no_overrides():
    cfg = EvaluatorConfig()
    assert cfg.thresholds.aprovacao_condicional_min == 50
    assert cfg.thresholds.aprovado_min == 75
    assert cfg.weights is None
    assert cfg.node_models == {}


def test_verdict_for_bands():
    cfg = EvaluatorConfig()
    assert cfg.verdict_for(49) is Verdict.REPROVADO
    assert cfg.verdict_for(50) is Verdict.APROVACAO_CONDICIONAL
    assert cfg.verdict_for(74) is Verdict.APROVACAO_CONDICIONAL
    assert cfg.verdict_for(75) is Verdict.APROVADO


def test_negative_weights_rejected_before_analysis():
    # CB-07: validação na construção da config, antes de qualquer análise
    with pytest.raises(ValidationError, match="CB-07"):
        EvaluatorConfig(weights={Dimension.CUSTO: -0.5, Dimension.ROBUSTEZ: 0.5})


def test_all_zero_weights_rejected():
    with pytest.raises(ValidationError, match="CB-07"):
        EvaluatorConfig(weights={Dimension.CUSTO: 0.0, Dimension.ROBUSTEZ: 0.0})


def test_unordered_thresholds_rejected():
    with pytest.raises(ValidationError):
        BandThresholds(aprovacao_condicional_min=80, aprovado_min=60)


def test_switching_provider_is_config_only():
    # RNF-06/RNF-12: trocar Anthropic→OpenRouter e o modelo é só dados de config
    node = NodeModelConfig(
        primary=ModelRef(backend=Backend.OPENROUTER, model="kimi-k2", base_url="https://x/api"),
        fallback=ModelRef(backend=Backend.ANTHROPIC, model="some-sonnet"),
    )
    cfg = EvaluatorConfig(node_models={"juiz_robustez": node})
    assert cfg.node_models["juiz_robustez"].primary.backend is Backend.OPENROUTER
    # temperatura padrão 0 (RNF-01)
    assert cfg.node_models["juiz_robustez"].fallback.temperature == 0.0


def test_config_is_frozen():
    cfg = EvaluatorConfig()
    with pytest.raises(ValidationError):
        cfg.confidence_floor = None  # type: ignore[misc]
