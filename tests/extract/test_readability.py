"""T-104 — Legibilidade (RF-03, CB-02): detecção determinística + impacto no TSM.

Nenhum arquivo é executado/importado (RNF-05): só leitura de texto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.enums import Dimension
from avalia.extract.readability import unreadable_files
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

_FIX = Path(__file__).resolve().parents[1] / "fixtures" / "ofuscado"


def _load() -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in _FIX.glob("*.py")}


def test_compiled_extension_is_unreadable():
    out = unreadable_files({"mod.pyc": "qualquer", "ok.py": "x = 1\n"})
    assert "mod.pyc" in out and "ok.py" not in out


def test_null_byte_is_unreadable():
    out = unreadable_files({"bin.py": "abc\x00def"})
    assert "bin.py" in out


def test_minified_long_line_is_unreadable():
    out = unreadable_files({"obf.py": "_=" + '"' + "a" * 2500 + '"'})
    assert "obf.py" in out


def test_normal_source_is_readable():
    assert unreadable_files({"clean.py": "def f():\n    return 1\n"}) == {}


def test_cb02_obfuscated_source_marks_unreadable_and_impacts_all_dims():
    tsm = build_tsm(_load(), EvaluatorConfig())
    # CB-02: o arquivo ofuscado é marcado ilegível e não entra na análise a fundo.
    unreadable = {ref.file_path for ref in tsm.readability.unreadable_files}
    assert "obf.py" in unreadable
    assert "obf.py" not in tsm.coverage.fully_analyzed
    # Código-fonte ilegível PODE conter agentes/prompts/loops/tools → impacta todas as dimensões.
    assert set(tsm.readability.impacted_dims) == set(Dimension)
    # o arquivo legível vizinho continua sendo analisado
    assert "main.py" in tsm.coverage.fully_analyzed


def test_cb02_unreadable_config_impacts_only_config_dependent_dims():
    # CB-02 escopado: um config quebrado toca só custo/performance/robustez (sinais
    # determinísticos derivados de config). NÃO colapsa as comportamentais nem a trajetória —
    # fim do falso "confiança baixa" global que um único arquivo quebrado produzia.
    tsm = build_tsm({"app.py": "x = 1\n", "settings.yaml": "a:\n  b: c: d\n"})
    unreadable = {ref.file_path for ref in tsm.readability.unreadable_files}
    assert "settings.yaml" in unreadable
    assert set(tsm.readability.impacted_dims) == {
        Dimension.CUSTO,
        Dimension.PERFORMANCE,
        Dimension.ROBUSTEZ,
    }


def test_broken_yaml_under_docs_is_ignored_not_unreadable():
    # Um YAML quebrado sob docs/ (ex.: spec de API) é documentação → ignorado, não ilegível:
    # não entra em unreadable, não é amostrado e não rebaixa confiança de nada.
    tsm = build_tsm({"app.py": "x = 1\n", "docs/api/openapi.yaml": "allOf:lixo\n  - a: b: c\n"})
    unreadable = {ref.file_path for ref in tsm.readability.unreadable_files}
    assert "docs/api/openapi.yaml" not in unreadable
    assert "docs/api/openapi.yaml" not in tsm.coverage.sampled
    assert tsm.readability.impacted_dims == []


def test_build_and_asset_files_are_out_of_scope_no_partial():
    # Dockerfile, shell, CSS, SVG não são código/config de agentes → fora de escopo, sem PARCIAL.
    tsm = build_tsm(
        {
            "app.py": "x = 1\n",
            "Dockerfile.api": "FROM python:3.12\n",
            "scripts/run.sh": "#!/bin/sh\necho hi\n",
            "web/styles.css": "body { color: red; }\n",
            "web/logo.svg": "<svg></svg>\n",
        }
    )
    assert tsm.coverage.sampled == []  # nada amostrado → laudo não será PARCIAL
