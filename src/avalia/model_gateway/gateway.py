"""T-007 — `ModelGateway`: acesso a modelo configurável/cross-provider (RNF-06, RNF-12).

Resolve `(tipo_de_nó, papel: primário|fallback)` → `ModelRef` concreto, isolando o resto do
código do provedor. Back-ends: Anthropic direto (padrão) e OpenRouter (base_url compatível
com OpenAI). Centraliza a política de retry/backoff (via config), a negociação de structured
output (`with_structured_output`, com degradação declarada → `StructuredOutputUnsupported`) e,
em `invoke_structured` (v1.4, plan §3.2c), a TRADUÇÃO das exceções reais do provedor em erros
tipados — sem ela, um 429 real abortava a avaliação (RNF-12/CB-10).

Default Opus→Sonnet (configurável por env/config — RNF-06): este é o ÚNICO lugar sancionado
onde slugs-padrão aparecem em código (diretório isento do guard de modelo), porque são
defaults sobrescrevíveis, não constantes espalhadas.

**Não executa, importa nem instancia o ALVO (RNF-05/S-04)** — só fala com modelos do AVALIA.

Rastreabilidade: RNF-06, RNF-12; resoluções #2, #2b; plan §3.2b.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from avalia.config.evaluator_config import (
    Backend,
    EvaluatorConfig,
    ModelRef,
    RetryPolicy,
)
from avalia.model_gateway.errors import ModelUnavailableError
from avalia.model_gateway.roles import ModelRole as ModelRole  # reexport (API estável)
from avalia.model_gateway.structured import StructuredInvoker

# Slugs-padrão (Opus→Sonnet). Sobrescrevíveis por env (RNF-06). Único ponto autorizado.
DEFAULT_PRIMARY_MODEL = "claude-opus-4-8"
DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-6"
ENV_PRIMARY = "AVALIA_DEFAULT_PRIMARY_MODEL"
ENV_FALLBACK = "AVALIA_DEFAULT_FALLBACK_MODEL"
ENV_BACKEND = "AVALIA_DEFAULT_BACKEND"
ENV_BASE_URL = "AVALIA_OPENROUTER_BASE_URL"
ENV_MAX_TOKENS = "AVALIA_DEFAULT_MAX_TOKENS"  # T3.1 — controle de custo (RF-DIM-C2)
ENV_TIMEOUT = "AVALIA_DEFAULT_TIMEOUT"  # T3.1 — controle de performance (RF-DIM-P2)
# Defaults dos controles de custo/performance das chamadas de juízo (sobrescrevíveis por env).
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT_S = 60.0


class StructuredOutputUnsupported(ModelUnavailableError):
    """Modelo/provedor não suporta `with_structured_output` → tratado como indisponível: o juiz
    (T-302) escala para o fallback declarado (RNF-12, passo 3)."""


ClientFactory = Callable[[ModelRef], Any]


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    """Lê inteiro positivo de env (RNF-06); valor inválido cai no default, sem quebrar."""
    raw = env.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _default_client_factory(ref: ModelRef) -> Any:
    """Constrói o cliente LangChain de forma PREGUIÇOSA (import só no acesso real).

    Nos testes o factory é injetado/mockado → langchain nem precisa estar instalado.
    Os kwargs vão num `dict[str, Any]` de propósito: a assinatura tipada de `ChatAnthropic`/
    `ChatOpenAI` varia entre versões do pacote (model vs. model_name, args nomeados obrigatórios),
    e acoplar o type-check a ela quebra o CI a cada bump. Desempacotar `**params` mantém o
    runtime idêntico e o mypy estável em qualquer versão instalada.
    """
    params: dict[str, Any] = {"model": ref.model, "temperature": ref.temperature}
    # T3.1 — repassa os controles de custo/performance quando definidos (RF-DIM-C2/P2). As chaves
    # de dict são propositais: além de configurarem a chamada, tornam o controle VISÍVEL à análise
    # estática (T4.2 lê `max_tokens`/`timeout` como chave de dict) — fecha o acoplamento T3↔T4.
    if ref.max_tokens is not None:
        params["max_tokens"] = ref.max_tokens
    if ref.timeout_s is not None:
        params["timeout"] = ref.timeout_s
    if ref.backend is Backend.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(**params)
    # OpenRouter expõe API compatível com OpenAI (alcance cross-provider — Kimi etc.).
    from langchain_openai import ChatOpenAI

    params["base_url"] = ref.base_url
    return ChatOpenAI(**params)


class ModelGateway(StructuredInvoker):
    """Porta única de acesso a modelos de julgamento do AVALIA."""

    def __init__(
        self,
        config: EvaluatorConfig | None = None,
        *,
        client_factory: ClientFactory | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config or EvaluatorConfig()
        self._client_factory = client_factory or _default_client_factory
        self._env = env if env is not None else os.environ

    def _default_ref(self, role: ModelRole) -> ModelRef:
        if role is ModelRole.PRIMARY:
            model = self._env.get(ENV_PRIMARY, DEFAULT_PRIMARY_MODEL)
        else:
            model = self._env.get(ENV_FALLBACK, DEFAULT_FALLBACK_MODEL)
        backend = Backend(self._env.get(ENV_BACKEND, Backend.ANTHROPIC.value))
        return ModelRef(
            backend=backend,
            model=model,
            base_url=self._env.get(ENV_BASE_URL),
            temperature=0.0,  # RNF-01
            max_tokens=_env_int(self._env, ENV_MAX_TOKENS, DEFAULT_MAX_TOKENS),  # T3.1
            timeout_s=_env_float(self._env, ENV_TIMEOUT, DEFAULT_TIMEOUT_S),  # T3.1
        )

    def resolve(self, node_type: str, role: ModelRole) -> ModelRef:
        """`(nó, papel)` → `ModelRef`. Config do nó tem prioridade; senão default Opus→Sonnet."""
        node_cfg = self._config.node_models.get(node_type)
        if node_cfg is not None:
            ref = node_cfg.primary if role is ModelRole.PRIMARY else node_cfg.fallback
            if ref is not None:
                return ref
        return self._default_ref(role)

    def retry_for(self, node_type: str) -> RetryPolicy:
        """Política de retry do nó (RNF-12) — de config ou default."""
        node_cfg = self._config.node_models.get(node_type)
        return node_cfg.retry if node_cfg is not None else RetryPolicy()

    def get_client(self, node_type: str, role: ModelRole) -> Any:
        """Cliente concreto para o papel. NÃO toca o alvo — só o modelo do AVALIA."""
        return self._client_factory(self.resolve(node_type, role))

    def with_structured_output(
        self, node_type: str, role: ModelRole, schema: Any, *, include_raw: bool = False
    ) -> Any:
        """Negocia structured output; degrada de forma DECLARADA se incompatível (RNF-12)."""
        client = self.get_client(node_type, role)
        fn = getattr(client, "with_structured_output", None)
        if not callable(fn):
            raise StructuredOutputUnsupported(
                f"Modelo '{self.resolve(node_type, role).model}' não expõe with_structured_output; "
                "o juiz (T-302) escala para o fallback declarado (passo 3 da RNF-12)."
            )
        return fn(schema, include_raw=True) if include_raw else fn(schema)

    def _bind(self, node_type: str, role: ModelRole, schema: Any) -> Any:
        """Vincula com `include_raw=True` (erro de parse como dado + uso de tokens). Falha ao
        CONSTRUIR o cliente (ex.: credencial ausente) = modelo indisponível → fallback (CB-10)."""
        try:
            return self.with_structured_output(node_type, role, schema, include_raw=True)
        except ModelUnavailableError:
            raise
        except Exception as exc:  # fronteira com o SDK (construção do cliente)
            raise ModelUnavailableError(
                f"falha ao preparar o modelo: {type(exc).__name__}: {exc}",
                origin=type(exc).__name__,
            ) from exc
