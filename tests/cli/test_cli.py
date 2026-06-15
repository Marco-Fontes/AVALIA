"""Smoke da CLI `avalia` (MVP): roda o avaliador sobre um diretório-alvo e grava o laudo.

Modo determinístico (sem gateway/LLM). Nada executa o alvo (RNF-05).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from avalia.cli import main

pytestmark = pytest.mark.fast

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "multiagente_loop_sem_teto"


def test_cli_generates_report_files_and_summary(tmp_path: Path, capsys):
    out = tmp_path / "laudo"
    rc = main([str(_FIXTURE), "--out", str(out), "--target-id", "demo"])
    assert rc == 0
    md, js = out / "laudo.md", out / "laudo.json"
    assert md.exists() and js.exists()
    # JSON é projeção fiel do contrato (carrega e tem o cabeçalho)
    data = json.loads(js.read_text(encoding="utf-8"))
    assert "header" in data and data["header"]["verdict"]
    # resumo no stdout
    captured = capsys.readouterr().out
    assert "AVALIA - resumo do laudo" in captured
    assert "Veredito" in captured


def test_cli_only_markdown_format(tmp_path: Path):
    out = tmp_path / "o"
    rc = main([str(_FIXTURE), "--out", str(out), "--format", "md"])
    assert rc == 0
    assert (out / "laudo.md").exists()
    assert not (out / "laudo.json").exists()


def test_cli_missing_path_returns_error(tmp_path: Path, capsys):
    rc = main([str(tmp_path / "nao-existe"), "--out", str(tmp_path / "o")])
    assert rc == 2
    assert "não encontrado" in capsys.readouterr().err


def test_cli_no_source_returns_error_without_report(tmp_path: Path, capsys):
    (tmp_path / "README.md").write_text("# só docs, sem código\n", encoding="utf-8")
    out = tmp_path / "o"
    rc = main([str(tmp_path), "--out", str(out)])
    assert rc == 2
    assert "código-fonte" in capsys.readouterr().err
    assert not out.exists()  # nenhum laudo gravado (CA-01)
