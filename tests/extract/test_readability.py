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


def test_cb02_obfuscated_fixture_marks_unreadable_and_impacts_all_dims():
    tsm = build_tsm(_load(), EvaluatorConfig())
    # CB-02: o arquivo ofuscado é marcado ilegível e não entra na análise a fundo.
    unreadable = {ref.file_path for ref in tsm.readability.unreadable_files}
    assert "obf.py" in unreadable
    assert "obf.py" not in tsm.coverage.fully_analyzed
    # Postura conservadora Fase 1: todas as 7 dimensões impactadas.
    assert set(tsm.readability.impacted_dims) == set(Dimension)
    # o arquivo legível vizinho continua sendo analisado
    assert "main.py" in tsm.coverage.fully_analyzed
