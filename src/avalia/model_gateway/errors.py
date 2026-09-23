"""Erros tipados de chamada a modelo + tradução das exceções reais do provedor (RNF-12, CB-10).

A política escalonada do juiz (retry → re-solicitação → fallback → parcial) só funciona se as
exceções dos SDKs (Anthropic/OpenAI via LangChain, httpx) chegarem CLASSIFICADAS. A classificação
é feita por `status_code` e pelo nome das classes na MRO — sem importar SDK nenhum (os back-ends
são importados de forma preguiçosa no gateway e podem nem estar instalados nos testes).

Três classes (plan §3.2c):
- **transitório** (limite de taxa, timeout, conexão, 5xx/529) → retry no MESMO modelo, com backoff;
- **indisponível** (400/401/403/404, modelo inexistente, autenticação) → fallback declarado;
- **malformado** (parse/validação da saída estruturada) → re-solicitação ao mesmo modelo.

Exceção desconhecida dentro da chamada ao modelo → indisponível (a avaliação nunca aborta por
falha pontual — CB-10), com o nome da classe preservado em `origin` para auditoria.

Não executa, importa nem instancia o ALVO (RNF-05) — só classifica erros do modelo do AVALIA.

Rastreabilidade: RNF-12, CB-10; plan §3.2c; T-302/T-1008 (DoD reforçado v1.4).
"""

from __future__ import annotations


class ModelCallError(RuntimeError):
    """Base dos erros de chamada a modelo. `origin` = nome da exceção original do provedor."""

    def __init__(self, message: str, *, origin: str | None = None) -> None:
        super().__init__(message)
        self.origin = origin


class TransientModelError(ModelCallError):
    """Erro transitório (rate limit, timeout, 5xx) → retry no mesmo modelo (RNF-12, passo 1)."""


class MalformedOutputError(ModelCallError):
    """Saída estruturada inválida → re-solicitação ao mesmo modelo (RNF-12, passo 2)."""


class ModelUnavailableError(ModelCallError):
    """Modelo indisponível → escala para o fallback (RNF-12, passo 3)."""


# Status HTTP (vide docs de erro da Anthropic/OpenAI): 408 timeout, 409 conflito, 429 limite de
# taxa, 5xx erro do servidor, 529 sobrecarga — todos com retry recomendado pelo provedor.
_TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
_UNAVAILABLE_STATUS = frozenset({400, 401, 403, 404, 422})

_MALFORMED_NAMES = frozenset({"OutputParserException", "ValidationError", "JSONDecodeError"})
_TRANSIENT_NAMES = frozenset(
    {
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "OverloadedError",
        "ServiceUnavailableError",
        "TimeoutException",  # httpx (base de ConnectTimeout/ReadTimeout/…)
        "ConnectError",  # httpx
        "RemoteProtocolError",  # httpx
    }
)
_UNAVAILABLE_NAMES = frozenset(
    {
        "NotFoundError",
        "AuthenticationError",
        "PermissionDeniedError",
        "BadRequestError",
        "UnprocessableEntityError",
    }
)


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def classify_provider_error(exc: BaseException) -> type[ModelCallError]:
    """Classe RNF-12 de uma exceção levantada DENTRO da chamada ao modelo."""
    if isinstance(exc, ModelCallError):
        return type(exc)
    names = {cls.__name__ for cls in type(exc).__mro__}
    if names & _MALFORMED_NAMES:
        return MalformedOutputError
    status = _status_code(exc)
    if status is not None:
        if status in _TRANSIENT_STATUS:
            return TransientModelError
        if status in _UNAVAILABLE_STATUS:
            return ModelUnavailableError
    if names & _UNAVAILABLE_NAMES:
        return ModelUnavailableError
    if names & _TRANSIENT_NAMES or isinstance(exc, TimeoutError | ConnectionError):
        return TransientModelError
    # Não reconhecida: trata como indisponível → fallback declarado (nunca aborta — CB-10).
    return ModelUnavailableError


def translate_provider_error(exc: BaseException) -> ModelCallError:
    """Converte a exceção do provedor no erro tipado correspondente (preserva o nome original)."""
    if isinstance(exc, ModelCallError):
        return exc
    cls = classify_provider_error(exc)
    return cls(f"{type(exc).__name__}: {exc}", origin=type(exc).__name__)
