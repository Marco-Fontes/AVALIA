"""Fase 1 Tier 1 — novos FindingTypes determinísticos (fatos que o builder esquece).

SEGREDO_HARDCODED (Segurança), MODELO_SEM_VERSAO_FIXA (Ciclo de vida), TOOL_SEM_SCHEMA
(Ferramentas). Cada um: dispara no caso-alvo, NÃO dispara no caso são. Nada executa o alvo.
"""

from __future__ import annotations

import pytest

from avalia.domain.taxonomy import FindingType
from avalia.evaluators.custo import evaluate_custo
from avalia.evaluators.robustez import evaluate_robustez
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast


def _has(dr, ft: FindingType) -> bool:
    return any(f.finding_type is ft for f in dr.findings)


# --- SEGREDO_HARDCODED -------------------------------------------------------
def test_hardcoded_secret_is_flagged():
    tsm = build_tsm({"settings.yaml": "api_key: sk-live-abc123\n"})
    assert _has(evaluate_robustez(tsm), FindingType.SEGREDO_HARDCODED)


def test_secret_from_env_is_not_flagged():
    # Valor vindo de variável de ambiente é boa prática → não é hardcode.
    tsm = build_tsm({"settings.yaml": "api_key: ${API_KEY}\n"})
    assert not _has(evaluate_robustez(tsm), FindingType.SEGREDO_HARDCODED)


def test_sensitive_named_code_constant_is_not_flagged():
    # Dogfood: constante de código com nome sensível (`SECRET_PATTERNS`, `_TOKEN_KEYS`) NÃO é
    # segredo — só escaneamos arquivos de config/dados, não fonte .py.
    src = 'SECRET_PATTERNS = ["sk-", "token="]\n_TOKEN_KEYS = ("max_tokens",)\n'
    tsm = build_tsm({"mod.py": src})
    assert not _has(evaluate_robustez(tsm), FindingType.SEGREDO_HARDCODED)


def test_ci_workflow_service_creds_are_not_flagged():
    # Credenciais de serviço em workflow de CI são descartáveis por convenção → fora do escopo.
    ci = "services:\n  pg:\n    env:\n      POSTGRES_PASSWORD: postgres\n"
    tsm = build_tsm({".github/workflows/ci.yml": ci})
    assert not _has(evaluate_robustez(tsm), FindingType.SEGREDO_HARDCODED)


# --- MODELO_SEM_VERSAO_FIXA --------------------------------------------------
def test_moving_model_alias_is_flagged():
    tsm = build_tsm({"config.yaml": "model: claude-3-5-sonnet-latest\n"})
    assert _has(evaluate_custo(tsm), FindingType.MODELO_SEM_VERSAO_FIXA)


def test_pinned_model_is_not_flagged():
    tsm = build_tsm({"config.yaml": "model: claude-opus-4-8\n"})
    assert not _has(evaluate_custo(tsm), FindingType.MODELO_SEM_VERSAO_FIXA)


def test_docker_latest_tag_is_not_a_model_alias():
    # Sem família de modelo reconhecida → não dispara (baixo ruído).
    tsm = build_tsm({"config.yaml": "image: python:3.12-latest\n"})
    assert not _has(evaluate_custo(tsm), FindingType.MODELO_SEM_VERSAO_FIXA)


# --- TOOL_SEM_SCHEMA ---------------------------------------------------------
_UNTYPED_TOOL = """
@tool
def search(query):
    return query
"""

_TYPED_TOOL = """
@tool
def search(query: str) -> str:
    return query
"""


def test_tool_without_typed_args_is_flagged():
    tsm = build_tsm({"tools.py": _UNTYPED_TOOL})
    assert tsm.tools and tsm.tools[0].has_schema is False
    assert _has(evaluate_trajetoria(tsm), FindingType.TOOL_SEM_SCHEMA)


def test_tool_with_typed_args_is_not_flagged():
    tsm = build_tsm({"tools.py": _TYPED_TOOL})
    assert tsm.tools and tsm.tools[0].has_schema is True
    assert not _has(evaluate_trajetoria(tsm), FindingType.TOOL_SEM_SCHEMA)
