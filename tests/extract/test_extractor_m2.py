"""M2 — extensões do extrator: token_limit, input_validation, fallback_modelo, harness.

Suporte determinístico aos avaliadores de Custo (C2), Robustez (R2/R3) e Qualidade (Q1/CA-06).
Tudo por leitura estática (`ast`) — nada executa o alvo.
"""

from __future__ import annotations

import pytest

from avalia.extract.python_extractor import PythonExtractor
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast


def _kinds(src: str) -> set[str]:
    r = PythonExtractor().extract({"alvo/main.py": src})
    return {e.kind for e in r.error_handling}


def test_detects_token_limit():
    assert "token_limit" in _kinds("resp = call(model=m, max_tokens=512)\n")


def test_detects_input_validation():
    assert "input_validation" in _kinds("def f(x):\n    return isinstance(x, str)\n")
    assert "input_validation" in _kinds("obj = Model.model_validate(data)\n")


def test_detects_model_fallback():
    assert "fallback_modelo" in _kinds("chain = base.with_fallbacks([alt])\n")
    assert "fallback_modelo" in _kinds("llm = make(model=m, fallback=other)\n")


def test_detects_retry_and_timeout_and_cache():
    src = (
        "from functools import lru_cache\n\n"
        "@lru_cache\n"
        "def cached():\n    return 1\n\n"
        "@retry\n"
        "def flaky():\n    return call(timeout=10)\n"
    )
    kinds = _kinds(src)
    assert {"cache", "retry", "timeout"} <= kinds


def test_has_harness_from_filenames():
    with_harness = build_tsm(
        {"main.py": "x = 1\n", "tests/test_main.py": "def test_x():\n    pass\n"}
    )
    without = build_tsm({"main.py": "x = 1\n"})
    assert with_harness.has_harness is True
    assert without.has_harness is False
