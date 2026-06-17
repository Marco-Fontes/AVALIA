"""T4.1/T4.2 — detecção de retry/fallback IMPERATIVOS e de max_tokens/timeout via dict/config.

Fixtures positivas e negativas (evitar falso negativo E falso positivo — §10 Riscos):
retry/fallback exigem padrão ESTRUTURAL (laço de tentativas / iteração por papéis), não a mera
presença de um nome solto. Nada executa o alvo (só `ast.parse`).
Rastreabilidade: RF-DIM-R2, RF-DIM-C2, RF-DIM-P2; RNF-12.
"""

from __future__ import annotations

import pytest

from avalia.extract.python_extractor import PythonExtractor

pytestmark = pytest.mark.fast


def _kinds(src: str) -> set[str]:
    r = PythonExtractor().extract({"alvo/m.py": src})
    return {e.kind for e in r.error_handling}


# ----------------------------- T4.1 retry -----------------------------

_RETRY_RANGE = """
def call(model, retry):
    for _ in range(retry.max_attempts):
        try:
            return model.invoke()
        except TransientError:
            continue
"""

_RETRY_WHILE_COUNTER = """
def call(model):
    attempt = 0
    while attempt < 3:
        attempt += 1
        try:
            return model.invoke()
        except Exception:
            continue
"""

_NO_RETRY = """
def sum_first(n):
    total = 0
    for i in range(n):
        total += i
    return total
"""


def test_retry_loop_with_attempt_bounds_detected():
    assert "retry" in _kinds(_RETRY_RANGE)


def test_retry_loop_with_try_continue_detected():
    assert "retry" in _kinds(_RETRY_WHILE_COUNTER)


def test_plain_loop_is_not_retry():
    assert "retry" not in _kinds(_NO_RETRY)


_RETRIEVER_LOOP = """
def search(retriever, query):
    for chunk in retriever.retrieve(query):
        use(chunk)
"""

_ENTRIES_LOOP = """
def process(self):
    for e in self.entries:
        handle(e)
"""


def test_retriever_iteration_is_not_retry():
    # "retr"/"tries" soltos casariam retriever/entries → mascarariam SEM_RETRY (falso positivo).
    assert "retry" not in _kinds(_RETRIEVER_LOOP)


def test_entries_iteration_is_not_retry():
    assert "retry" not in _kinds(_ENTRIES_LOOP)


# ----------------------------- T4.1 fallback de modelo -----------------------------

_FALLBACK_ROLES = """
def judge(gateway):
    for role in (ModelRole.PRIMARY, ModelRole.FALLBACK):
        client = gateway.get_client(role)
        return client.invoke()
"""

_NO_FALLBACK_NAME_ONLY = """
def setup():
    fallbacks = [1, 2, 3]
    for x in fallbacks:
        print(x)
"""


def test_fallback_role_iteration_detected():
    assert "fallback_modelo" in _kinds(_FALLBACK_ROLES)


def test_iterating_unrelated_list_named_fallbacks_is_not_fallback_model():
    # "fallback" no nome, mas sem contexto de papel/modelo → não é fallback de modelo (§10).
    assert "fallback_modelo" not in _kinds(_NO_FALLBACK_NAME_ONLY)


# ----------------------------- T4.2 max_tokens / timeout -----------------------------

_DICT_PARAMS = """
def build(ref):
    params = {"model": ref.model, "max_tokens": 1024}
    params["timeout"] = 60
    return Client(**params)
"""

_CONFIG_FIELD = """
class ModelRef:
    max_tokens: int | None = 1024
    timeout_s: float | None = 60.0
"""

_NO_LIMITS = """
def build(ref):
    return Client(model=ref.model)
"""


def test_token_limit_and_timeout_via_dict_and_subscript():
    kinds = _kinds(_DICT_PARAMS)
    assert "token_limit" in kinds
    assert "timeout" in kinds


def test_token_limit_and_timeout_via_config_field():
    kinds = _kinds(_CONFIG_FIELD)
    assert "token_limit" in kinds
    assert "timeout" in kinds


def test_absent_limits_not_detected():
    kinds = _kinds(_NO_LIMITS)
    assert "token_limit" not in kinds
    assert "timeout" not in kinds


# ----------------------------- T3.2 cache (classe *Cache) -----------------------------

_CACHE_CLASS = """
class JudgeCache:
    def __init__(self):
        self._store = {}
"""

_DECORATOR_CACHE = """
from functools import lru_cache


@lru_cache
def lookup(x):
    return x
"""


def test_cache_class_detected():
    assert "cache" in _kinds(_CACHE_CLASS)


def test_decorator_cache_still_detected():
    assert "cache" in _kinds(_DECORATOR_CACHE)


def test_no_cache_when_absent():
    assert "cache" not in _kinds("class Foo:\n    pass\n")
