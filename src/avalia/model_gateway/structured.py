"""Invocação estruturada com tradução de erros (RNF-12) — `invoke_structured` (plan §3.2c).

`StructuredInvoker` é a base de todo gateway de juízo (o `ModelGateway` real e os dublês de
teste): dado um cliente já vinculado ao schema (`_bind`), chama o modelo, traduz as exceções do
provedor em erros tipados (`errors.py`) e normaliza a saída num `StructuredCallResult`.

Aceita as duas formas de retorno de `with_structured_output`: com `include_raw=True` (dict
`raw`/`parsed`/`parsing_error` — o erro de parse vira DADO, e o uso de tokens fica disponível para
o orçamento) ou o objeto já parseado. Saída ausente ou de tipo errado → `MalformedOutputError`.

Não executa, importa nem instancia o ALVO (RNF-05). Rastreabilidade: RNF-12, CB-10; plan §3.2c.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from avalia.model_gateway.errors import (
    MalformedOutputError,
    ModelCallError,
    translate_provider_error,
)
from avalia.model_gateway.roles import ModelRole


class StructuredCallResult(BaseModel):
    """Resultado de uma chamada de juízo: saída parseada + uso de tokens (0 se não reportado) +
    slug do modelo que respondeu (para precificar a chamada — DQ-01; `None` se desconhecido)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    parsed: Any
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None


def _usage(raw: Any) -> tuple[int, int]:
    meta = getattr(raw, "usage_metadata", None)
    if not isinstance(meta, Mapping):
        return 0, 0
    return int(meta.get("input_tokens") or 0), int(meta.get("output_tokens") or 0)


def normalize_structured_output(out: Any, schema: Any) -> StructuredCallResult:
    """Normaliza o retorno do cliente; saída inválida → `MalformedOutputError` (re-solicitar)."""
    raw: Any = None
    parsed: Any = out
    if isinstance(out, Mapping) and "parsed" in out:
        error = out.get("parsing_error")
        if error is not None:
            raise MalformedOutputError(
                f"saída estruturada inválida: {error}", origin=type(error).__name__
            )
        raw, parsed = out.get("raw"), out.get("parsed")
    if parsed is None or (isinstance(schema, type) and not isinstance(parsed, schema)):
        raise MalformedOutputError(
            f"saída estruturada ausente ou de tipo inesperado ({type(parsed).__name__})"
        )
    input_tokens, output_tokens = _usage(raw)
    return StructuredCallResult(
        parsed=parsed, input_tokens=input_tokens, output_tokens=output_tokens
    )


class StructuredInvoker:
    """Base de gateway de juízo: `invoke_structured` sobre o `_bind` de cada implementação."""

    def with_structured_output(self, node_type: str, role: ModelRole, schema: Any) -> Any:
        raise NotImplementedError

    def _model_name(self, node_type: str, role: ModelRole) -> str | None:
        """Slug do modelo que atende `(nó, papel)`, se conhecido (dublês: `None`)."""
        return None

    def _bind(self, node_type: str, role: ModelRole, schema: Any) -> Any:
        """Cliente vinculado ao schema. Default: `with_structured_output` (dublês de teste)."""
        return self.with_structured_output(node_type, role, schema)

    def invoke_structured(
        self, node_type: str, role: ModelRole, schema: Any, messages: list[dict[str, str]]
    ) -> StructuredCallResult:
        """Chama o modelo; erros do provedor saem TIPADOS (transitório/indisponível/malformado)."""
        bound = self._bind(node_type, role, schema)
        try:
            out = bound.invoke(messages)
        except ModelCallError:
            raise
        except Exception as exc:  # fronteira com o SDK: toda falha da chamada é classificada
            raise translate_provider_error(exc) from exc
        result = normalize_structured_output(out, schema)
        return result.model_copy(update={"model": self._model_name(node_type, role)})
