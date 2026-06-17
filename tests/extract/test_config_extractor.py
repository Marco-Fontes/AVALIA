"""T1.5 — testes do `ConfigExtractor` (YAML/JSON/TOML/INI/`.env`) e do roteamento no TSM.

DoD (PLANO-MELHORIAS §3):
- cada formato vira `ConfigItem`s com símbolo = caminho da chave (achatado);
- arquivo malformado → `unreadable` (sem exceção);
- um projeto com `*.yaml` deixa de cair em `coverage.sampled` (fim do parcial espúrio);
- nada executa o alvo (só parsing de dados).
Rastreabilidade: RF-01, RF-12, RF-14, RNF-07.
"""

from __future__ import annotations

import pytest

from avalia.extract.config_extractor import ConfigExtractor
from avalia.extract.registry import get_extractor, language_for_path
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

_YAML = """
rag:
  alucinacao: 0.3
  robustez: 0.2
modelos:
  - opus
  - sonnet
"""

_JSON = '{"service": {"timeout": 30, "retries": 2}, "flags": ["a", "b"]}'

_TOML = """
[tool.pytest]
addopts = "-q"

[build]
target = "py312"
"""

_INI = """
[pytest]
addopts = -q

[flake8]
max-line-length = 100
"""

_ENV = """
# comentário
export API_HOST=localhost
MAX_TOKENS=1024
EMPTY=
"""


def test_registry_routes_config_extensions():
    for path in ("x.yaml", "x.yml", "x.json", "x.toml", "x.ini", "x.cfg", "x.env"):
        assert language_for_path(path) == "config"
    assert get_extractor("config") is not None
    assert language_for_path("x.py") == "python"  # inalterado


def test_yaml_produces_flattened_config_items():
    r = ConfigExtractor().extract({"config/weights.yaml": _YAML})
    keys = {c.key for c in r.configs}
    assert "rag.alucinacao" in keys
    assert "rag.robustez" in keys
    assert "modelos" in keys  # lista de escalares → chave-pai resumida
    item = next(c for c in r.configs if c.key == "rag.alucinacao")
    assert item.evidence.symbol == "rag.alucinacao"
    assert item.evidence.component_kind == "config"
    assert "config/weights.yaml" in r.files


def test_json_toml_ini_env_each_yield_items():
    rj = ConfigExtractor().extract({"a.json": _JSON})
    assert {"service.timeout", "service.retries"} <= {c.key for c in rj.configs}

    rt = ConfigExtractor().extract({"pyproject.toml": _TOML})
    assert "tool.pytest.addopts" in {c.key for c in rt.configs}

    ri = ConfigExtractor().extract({"setup.cfg": _INI})
    assert "pytest.addopts" in {c.key for c in ri.configs}

    re_ = ConfigExtractor().extract({".env": _ENV})
    env_keys = {c.key for c in re_.configs}
    assert "API_HOST" in env_keys and "MAX_TOKENS" in env_keys


def test_malformed_config_marked_unreadable_without_crash():
    r = ConfigExtractor().extract({"broken.json": "{not: valid json,,,"})
    assert r.unreadable_files == ["broken.json"]
    assert r.configs == []


def test_lock_files_are_ignored_not_parsed_as_config():
    # Lock files (mesmo com extensão de config) são dados gerados → ignorados, não parseados (§10).
    tsm = build_tsm(
        {
            "app.py": "X = 1\n",
            "package-lock.json": '{"name": "x", "dependencies": {"a": {"version": "1.0.0"}}}',
            "pnpm-lock.yaml": "lockfileVersion: 9\npackages:\n  a:\n    version: 1.0.0\n",
        }
    )
    assert "package-lock.json" not in tsm.coverage.fully_analyzed
    assert "pnpm-lock.yaml" not in tsm.coverage.fully_analyzed
    assert "package-lock.json" not in tsm.coverage.sampled  # ignorado, não amostrado
    lock_files = {"package-lock.json", "pnpm-lock.yaml"}
    assert not [c for c in tsm.configs if c.evidence.file_path in lock_files]  # zero ruído


def test_tsm_routes_yaml_out_of_sampling():
    # Projeto Python + YAML de config: o YAML é analisado (não amostrado) → sem parcial espúrio.
    tsm = build_tsm({"app.py": "X = 1\n", "config/weights.yaml": _YAML})
    assert "config/weights.yaml" in tsm.coverage.fully_analyzed
    assert "config/weights.yaml" not in tsm.coverage.sampled
    assert tsm.coverage.sampled == []  # nada amostrado → laudo não será PARCIAL por config
    assert any(c.key == "rag.alucinacao" for c in tsm.configs)
