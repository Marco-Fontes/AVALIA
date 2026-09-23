"""T-302 / T-1008 (DoD reforçado v1.4) — política escalonada do juiz diante de falhas REAIS.

Usa o `ModelGateway` de verdade com uma fábrica de cliente falsa que levanta exceções com a
forma dos SDKs (nome + `status_code`). O relógio do backoff é falso (registra as esperas).
Nenhum modelo real; nada executa o alvo (RNF-05).

Rastreabilidade: RNF-12 (passos 1–4), CB-10, RNF-08/RNF-09 (substituição declarada).
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig, NodeModelConfig, RetryPolicy
from avalia.domain.enums import Band, Confidence, Dimension
from avalia.domain.evidence import EvidenceRef
from avalia.judge.framework import Judge, JudgeVerdict
from avalia.judge.rubrics import get_rubric
from avalia.model_gateway.gateway import DEFAULT_PRIMARY_MODEL, ModelGateway

pytestmark = pytest.mark.fast

_NODE = "juiz_trajetoria"
_EV = [EvidenceRef(file_path="main.py", symbol="tool_x", component_kind="tool")]


class RateLimitError(Exception):
    status_code = 429


class NotFoundError(Exception):
    status_code = 404


class AuthenticationError(Exception):
    status_code = 401


class WeirdSDKError(Exception): ...


class OutputParserException(ValueError): ...


def _verdict(conf: Confidence = Confidence.ALTO) -> JudgeVerdict:
    return JudgeVerdict(
        score=64, band=Band.ADEQUADO_COM_RESSALVAS, confidence=conf, reasoning="segundo a rubrica"
    )


def _ok(conf: Confidence = Confidence.ALTO):
    return {"raw": None, "parsed": _verdict(conf), "parsing_error": None}


class _Script:
    """Sequência de comportamentos por papel (primário/fallback); o último se repete."""

    def __init__(self, primary: list, fallback: list | None = None) -> None:
        self._queues = {"primary": list(primary), "fallback": list(fallback or [_ok])}
        self.calls = {"primary": 0, "fallback": 0}

    def next(self, role: str):
        self.calls[role] += 1
        queue = self._queues[role]
        step = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(step, BaseException):
            raise step
        return step()


class _Client:
    def __init__(self, script: _Script, role: str) -> None:
        self._script, self._role = script, role

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, messages):
        return self._script.next(self._role)


def _judge(script: _Script, *, retry: RetryPolicy, sleeps: list[float]) -> Judge:
    def factory(ref):
        role = "primary" if ref.model == DEFAULT_PRIMARY_MODEL else "fallback"
        return _Client(script, role)

    config = EvaluatorConfig(node_models={_NODE: NodeModelConfig(retry=retry)})
    gateway = ModelGateway(config, client_factory=factory, env={})
    return Judge(gateway, _NODE, sleep=sleeps.append)


def _assess(judge: Judge):
    return judge.assess(
        dimension=Dimension.TRAJETORIA,
        rubric=get_rubric("trajetoria/v1"),
        instruction="Avalie a Trajetória.",
        angles=["cetico"],
        target_content={"main.py": "x = 1"},
        evidence=_EV,
    )


_RETRY3 = RetryPolicy(max_attempts=3, backoff_seconds=1.0, max_backoff_seconds=30.0)


def test_rate_limit_retries_same_model_with_backoff():
    sleeps: list[float] = []
    script = _Script(primary=[RateLimitError("429"), _ok])
    contrib = _assess(_judge(script, retry=_RETRY3, sleeps=sleeps))
    assert contrib.opinions and contrib.opinions[0].score == 64
    assert sleeps == [1.0]  # (1) esperou antes da retentativa
    assert script.calls == {"primary": 2, "fallback": 0}
    assert contrib.model_substitutions == [] and not contrib.partial


def test_persistent_rate_limit_escalates_to_declared_fallback():
    sleeps: list[float] = []
    script = _Script(primary=[RateLimitError("429")])
    contrib = _assess(_judge(script, retry=_RETRY3, sleeps=sleeps))
    assert sleeps == [1.0, 2.0]  # exponencial; sem espera após a última tentativa
    assert script.calls == {"primary": 3, "fallback": 1}
    assert contrib.model_substitutions == [
        "fallback de modelo aplicado (primário: transitório após 3 tentativa(s) — RateLimitError)"
    ]
    assert contrib.confidence is Confidence.MEDIO  # reduzida de ALTO (RNF-12, passo 3)


def test_not_found_goes_to_fallback_without_retry_or_wait():
    sleeps: list[float] = []
    script = _Script(primary=[NotFoundError("modelo inexistente")])
    contrib = _assess(_judge(script, retry=_RETRY3, sleeps=sleeps))
    assert sleeps == [] and script.calls["primary"] == 1
    assert contrib.model_substitutions == [
        "fallback de modelo aplicado (primário: indisponível — NotFoundError)"
    ]


def test_auth_failure_on_both_models_signals_partial_without_raising():
    script = _Script(primary=[AuthenticationError("401")], fallback=[AuthenticationError("401")])
    contrib = _assess(_judge(script, retry=_RETRY3, sleeps=[]))
    assert contrib.partial is True and contrib.opinions == []  # (4) → laudo parcial (CB-10)


def test_parsing_error_is_resolicited_without_backoff():
    sleeps: list[float] = []
    bad = {"raw": None, "parsed": None, "parsing_error": OutputParserException("json")}
    script = _Script(primary=[lambda: bad, _ok])
    contrib = _assess(_judge(script, retry=_RETRY3, sleeps=sleeps))
    assert contrib.opinions and sleeps == []  # (2) re-solicitação, sem espera
    assert script.calls["primary"] == 2 and contrib.model_substitutions == []


def test_unknown_sdk_exception_falls_back_with_its_name():
    script = _Script(primary=[WeirdSDKError("?")])
    contrib = _assess(_judge(script, retry=_RETRY3, sleeps=[]))
    assert contrib.opinions
    assert contrib.model_substitutions == [
        "fallback de modelo aplicado (primário: indisponível — WeirdSDKError)"
    ]
