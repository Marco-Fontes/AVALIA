"""T-007 — testes do ModelGateway (RNF-06, RNF-12; resoluções #2, #2b).

DoD: trocar Anthropic↔OpenRouter e o modelo de fallback é só configuração; default Opus→Sonnet
ativo quando nada é configurado; structured output funciona OU degrada de forma declarada.
Factory de cliente é MOCKADO — nenhum modelo real, langchain nem precisa estar instalado, e
nada toca o ALVO.
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import (
    Backend,
    EvaluatorConfig,
    ModelRef,
    NodeModelConfig,
    RetryPolicy,
)
from avalia.model_gateway.gateway import (
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_PRIMARY_MODEL,
    ModelGateway,
    ModelRole,
    StructuredOutputUnsupported,
)

pytestmark = pytest.mark.fast


class _FakeClient:
    """Cliente falso que registra a chamada de structured output."""

    def __init__(self, ref: ModelRef) -> None:
        self.ref = ref
        self.bound_schema: object | None = None

    def with_structured_output(self, schema: object) -> _FakeClient:
        self.bound_schema = schema
        return self


class _DumbClient:
    """Cliente sem with_structured_output (provedor incompatível)."""

    def __init__(self, ref: ModelRef) -> None:
        self.ref = ref


def _gw(config: EvaluatorConfig | None = None, factory=_FakeClient, env=None) -> ModelGateway:
    return ModelGateway(config, client_factory=factory, env=env or {})


def test_default_is_opus_then_sonnet_anthropic():
    gw = _gw()
    primary = gw.resolve("juiz_trajetoria", ModelRole.PRIMARY)
    fallback = gw.resolve("juiz_trajetoria", ModelRole.FALLBACK)
    assert primary.model == DEFAULT_PRIMARY_MODEL and "opus" in primary.model.lower()
    assert fallback.model == DEFAULT_FALLBACK_MODEL and "sonnet" in fallback.model.lower()
    assert primary.backend is Backend.ANTHROPIC
    assert primary.temperature == 0.0  # RNF-01


def test_env_overrides_default_models():
    gw = _gw(
        env={"AVALIA_DEFAULT_PRIMARY_MODEL": "some-primary", "AVALIA_DEFAULT_BACKEND": "openrouter"}
    )
    primary = gw.resolve("qualquer_no", ModelRole.PRIMARY)
    assert primary.model == "some-primary"
    assert primary.backend is Backend.OPENROUTER


def test_switching_provider_is_config_only():
    # RNF-06/RNF-12: o avaliador não muda; só a config do nó muda o provedor/modelo
    node = NodeModelConfig(
        primary=ModelRef(backend=Backend.OPENROUTER, model="kimi-k2", base_url="https://or/api"),
        fallback=ModelRef(backend=Backend.ANTHROPIC, model="outro-sonnet"),
        retry=RetryPolicy(max_attempts=3, backoff_seconds=2.0),
    )
    gw = _gw(EvaluatorConfig(node_models={"juiz_robustez": node}))
    assert gw.resolve("juiz_robustez", ModelRole.PRIMARY).model == "kimi-k2"
    assert gw.resolve("juiz_robustez", ModelRole.FALLBACK).model == "outro-sonnet"
    # nó sem config cai no default Opus→Sonnet
    assert gw.resolve("juiz_custo", ModelRole.PRIMARY).model == DEFAULT_PRIMARY_MODEL


def test_retry_for_reads_config_or_default():
    node = NodeModelConfig(retry=RetryPolicy(max_attempts=5))
    gw = _gw(EvaluatorConfig(node_models={"n": node}))
    assert gw.retry_for("n").max_attempts == 5
    assert gw.retry_for("desconhecido").max_attempts == 2  # default


def test_structured_output_uses_factory_and_binds_schema():
    gw = _gw()
    schema = {"type": "object"}
    bound = gw.with_structured_output("juiz_trajetoria", ModelRole.PRIMARY, schema)
    assert isinstance(bound, _FakeClient)
    assert bound.bound_schema is schema  # negociação chamou with_structured_output


def test_structured_output_degrades_declared_when_unsupported():
    gw = _gw(factory=_DumbClient)
    with pytest.raises(StructuredOutputUnsupported, match="RNF-12"):
        gw.with_structured_output("juiz_trajetoria", ModelRole.PRIMARY, {"type": "object"})
