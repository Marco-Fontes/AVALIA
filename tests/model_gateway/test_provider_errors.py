"""T-302 / T-1008 (DoD reforçado v1.4, plan §3.2c) — tradução das exceções REAIS do provedor.

As exceções abaixo são dublês locais com a MESMA FORMA dos SDKs (nome de classe e `status_code`
do `anthropic`/`openai`, `httpx`, LangChain): a classificação é por forma, sem importar SDK.
Nenhum modelo real é chamado e nada executa o alvo (RNF-05).

Rastreabilidade: RNF-12, CB-10.
"""

from __future__ import annotations

import json

import pytest

from avalia.config.evaluator_config import RetryPolicy
from avalia.domain.enums import Band, Confidence
from avalia.judge.framework import JudgeVerdict
from avalia.model_gateway.errors import (
    MalformedOutputError,
    ModelUnavailableError,
    TransientModelError,
    classify_provider_error,
    translate_provider_error,
)
from avalia.model_gateway.gateway import ModelGateway, ModelRole, StructuredOutputUnsupported
from avalia.model_gateway.structured import normalize_structured_output

pytestmark = pytest.mark.fast


# ---------- dublês com a forma das exceções dos SDKs ----------


class APIStatusError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(APIStatusError): ...


class InternalServerError(APIStatusError): ...


class OverloadedError(APIStatusError): ...


class NotFoundError(APIStatusError): ...


class AuthenticationError(APIStatusError): ...


class BadRequestError(APIStatusError): ...


class APITimeoutError(Exception): ...


class APIConnectionError(Exception): ...


class TimeoutException(Exception): ...  # httpx


class OutputParserException(ValueError): ...  # langchain_core


class _Response:
    status_code = 503


class HTTPStatusError(Exception):  # status só no `response` (httpx)
    response = _Response()


class WeirdSDKError(Exception): ...


def _validation_error() -> Exception:
    try:
        JudgeVerdict.model_validate({})
    except Exception as exc:  # pydantic.ValidationError real
        return exc
    raise AssertionError("esperava ValidationError")


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RateLimitError("429", 429), TransientModelError),
        (InternalServerError("500", 500), TransientModelError),
        (OverloadedError("529", 529), TransientModelError),
        (APITimeoutError("timeout"), TransientModelError),
        (APIConnectionError("reset"), TransientModelError),
        (TimeoutException("read timeout"), TransientModelError),
        (TimeoutError(), TransientModelError),
        (ConnectionResetError(), TransientModelError),
        (HTTPStatusError(), TransientModelError),
        (NotFoundError("modelo inexistente", 404), ModelUnavailableError),
        (AuthenticationError("sem chave", 401), ModelUnavailableError),
        (BadRequestError("contexto longo demais", 400), ModelUnavailableError),
        (OutputParserException("json inválido"), MalformedOutputError),
        (json.JSONDecodeError("x", "doc", 0), MalformedOutputError),
        (_validation_error(), MalformedOutputError),
        (WeirdSDKError("?"), ModelUnavailableError),  # desconhecida → fallback, nunca aborta
    ],
)
def test_classify_provider_error(exc, expected):
    assert classify_provider_error(exc) is expected


def test_translate_preserves_original_name_and_passes_typed_errors_through():
    translated = translate_provider_error(RateLimitError("limite", 429))
    assert isinstance(translated, TransientModelError)
    assert translated.origin == "RateLimitError"
    own = ModelUnavailableError("já tipado")
    assert translate_provider_error(own) is own


def test_structured_unsupported_is_treated_as_unavailable():
    assert issubclass(StructuredOutputUnsupported, ModelUnavailableError)


# ---------- normalização da saída estruturada ----------


def _verdict() -> JudgeVerdict:
    return JudgeVerdict(
        score=60, band=Band.ADEQUADO_COM_RESSALVAS, confidence=Confidence.MEDIO, reasoning="r"
    )


class _AIMessage:
    def __init__(self, usage: dict[str, int] | None) -> None:
        self.usage_metadata = usage


def test_normalize_include_raw_extracts_usage():
    out = {
        "raw": _AIMessage({"input_tokens": 120, "output_tokens": 30}),
        "parsed": _verdict(),
        "parsing_error": None,
    }
    result = normalize_structured_output(out, JudgeVerdict)
    assert isinstance(result.parsed, JudgeVerdict)
    assert (result.input_tokens, result.output_tokens) == (120, 30)


def test_normalize_parsing_error_is_malformed():
    out = {"raw": _AIMessage(None), "parsed": None, "parsing_error": OutputParserException("x")}
    with pytest.raises(MalformedOutputError):
        normalize_structured_output(out, JudgeVerdict)


def test_normalize_wrong_type_is_malformed():
    with pytest.raises(MalformedOutputError):
        normalize_structured_output({"score": 10}, JudgeVerdict)


def test_normalize_plain_parsed_object_has_zero_usage():
    result = normalize_structured_output(_verdict(), JudgeVerdict)
    assert (result.input_tokens, result.output_tokens) == (0, 0)


# ---------- ModelGateway.invoke_structured ----------


class _Runnable:
    def __init__(self, behavior) -> None:
        self._behavior = behavior

    def invoke(self, messages):
        return self._behavior()


class _Client:
    def __init__(self, behavior) -> None:
        self._behavior = behavior
        self.include_raw: bool | None = None

    def with_structured_output(self, schema, include_raw: bool = False):
        self.include_raw = include_raw
        return _Runnable(self._behavior)


def _gateway(behavior, clients: list | None = None) -> ModelGateway:
    def factory(ref):
        client = _Client(behavior)
        if clients is not None:
            clients.append(client)
        return client

    return ModelGateway(client_factory=factory, env={})


_MSGS = [{"role": "user", "content": "x"}]


def test_invoke_structured_binds_with_include_raw_and_returns_usage():
    clients: list = []
    gw = _gateway(
        lambda: {"raw": _AIMessage({"input_tokens": 5, "output_tokens": 2}), "parsed": _verdict()},
        clients,
    )
    result = gw.invoke_structured("juiz_x", ModelRole.PRIMARY, JudgeVerdict, _MSGS)
    assert clients[0].include_raw is True
    assert result.input_tokens == 5 and result.output_tokens == 2


def test_invoke_structured_translates_sdk_exception():
    def boom():
        raise RateLimitError("limite", 429)

    with pytest.raises(TransientModelError) as info:
        _gateway(boom).invoke_structured("juiz_x", ModelRole.PRIMARY, JudgeVerdict, _MSGS)
    assert info.value.origin == "RateLimitError"
    assert isinstance(info.value.__cause__, RateLimitError)  # causa original preservada


def test_client_construction_failure_is_unavailable():
    def factory(ref):
        raise ValueError("ANTHROPIC_API_KEY ausente")

    gw = ModelGateway(client_factory=factory, env={})
    with pytest.raises(ModelUnavailableError) as info:
        gw.invoke_structured("juiz_x", ModelRole.PRIMARY, JudgeVerdict, _MSGS)
    assert info.value.origin == "ValueError"


def test_retry_policy_backoff_is_exponential_and_capped():
    policy = RetryPolicy(max_attempts=4, backoff_seconds=10.0, max_backoff_seconds=25.0)
    assert [policy.delay_for(i) for i in range(3)] == [10.0, 20.0, 25.0]
