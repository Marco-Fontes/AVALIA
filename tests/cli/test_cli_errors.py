"""PR-6 (v1.4) — CLI com erros tratados e códigos de saída estáveis (RNF-11: baixa fricção).

0 sucesso · 1 erro interno (dica de --debug) · 2 entrada inválida · 3 infraestrutura (Postgres).
Antes, só `FileNotFoundError` era tratado: `--max-files 0`, DSN inválido ou pasta sem permissão
terminavam em traceback. Nada executa o alvo (RNF-05).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import avalia.cli as cli
from avalia.cli import EXIT_INFRA, EXIT_INPUT, EXIT_INTERNAL, main

pytestmark = pytest.mark.fast

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "multiagente_loop_sem_teto"


@pytest.fixture(autouse=True)
def _no_pg_dsn(monkeypatch):
    monkeypatch.delenv("AVALIA_PG_DSN", raising=False)


def _fixture() -> str:
    assert _FIXTURE.exists(), _FIXTURE
    return str(_FIXTURE)


@pytest.mark.parametrize("flag", [["--max-files", "0"], ["--token-ceiling", "0"]])
def test_invalid_config_is_input_error_without_traceback(tmp_path: Path, capsys, flag):
    rc = main([_fixture(), "--out", str(tmp_path / "o"), *flag])
    err = capsys.readouterr().err
    assert rc == EXIT_INPUT
    assert "configuração inválida" in err and "Traceback" not in err


def test_unwritable_output_is_input_error(tmp_path: Path, capsys):
    blocker = tmp_path / "arquivo"
    blocker.write_text("x", encoding="utf-8")
    rc = main([_fixture(), "--out", str(blocker / "sub")])  # pai é arquivo → OSError
    assert rc == EXIT_INPUT
    assert "não foi possível gravar o laudo" in capsys.readouterr().err


def test_unusable_history_dir_is_input_error(tmp_path: Path, capsys):
    blocker = tmp_path / "arquivo"
    blocker.write_text("x", encoding="utf-8")
    rc = main([_fixture(), "--out", str(tmp_path / "o"), "--history-dir", str(blocker / "h")])
    assert rc == EXIT_INPUT
    assert "diretório de histórico" in capsys.readouterr().err


class OperationalError(Exception):
    """Mesma forma do erro de conexão do driver (módulo `psycopg`), sem rede nem driver."""


OperationalError.__module__ = "psycopg"


def test_unreachable_postgres_is_infra_error(tmp_path: Path, capsys, monkeypatch):
    import avalia.persistence.postgres as pg

    def refuse(dsn, **kwargs):
        raise OperationalError("connection refused")

    monkeypatch.setattr(pg, "PostgresReportRepository", refuse)
    monkeypatch.setenv("AVALIA_PG_DSN", "postgresql://u:p@127.0.0.1:1/db")
    rc = main([_fixture(), "--out", str(tmp_path / "o")])
    assert rc == EXIT_INFRA
    assert "AVALIA_PG_DSN" in capsys.readouterr().err


def test_unexpected_error_is_internal_with_debug_hint(tmp_path: Path, capsys, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(cli, "build_avalia_graph", boom)
    rc = main([_fixture(), "--out", str(tmp_path / "o")])
    err = capsys.readouterr().err
    assert rc == EXIT_INTERNAL
    assert "Erro interno inesperado" in err and "--debug" in err and "Traceback" not in err

    rc = main([_fixture(), "--out", str(tmp_path / "o"), "--debug"])
    assert rc == EXIT_INTERNAL
    assert "Traceback" in capsys.readouterr().err  # --debug mostra o rastreamento


def test_database_error_during_run_is_infra_error(tmp_path: Path, capsys, monkeypatch):
    def boom(**kwargs):
        raise OperationalError("server closed the connection")

    monkeypatch.setattr(cli, "build_avalia_graph", boom)
    rc = main([_fixture(), "--out", str(tmp_path / "o")])
    assert rc == EXIT_INFRA
    assert "Postgres" in capsys.readouterr().err
