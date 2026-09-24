"""DQ-01 — tabela de preços por modelo lida de arquivo (torna o teto em moeda efetivo pelo CLI).

Preços são dado do operador (RNF-06), nunca embutidos no código. Os slugs abaixo são fictícios.
Nada executa o alvo (RNF-05); nenhum modelo real é chamado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.cli import _build_parser, _make_config, _price_warnings, main
from avalia.config.evaluator_config import EvaluatorConfig, ModelPrice
from avalia.config.model_prices import ENV_MODEL_PRICES, ModelPricesError, load_model_prices
from avalia.model_gateway.gateway import DEFAULT_FALLBACK_MODEL, DEFAULT_PRIMARY_MODEL, ModelGateway

pytestmark = pytest.mark.fast

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "multiagente_loop_sem_teto"
_YAML = (
    "modelo-a:\n  input_per_mtok: 3.0\n  output_per_mtok: 15.0\n"
    "modelo-b:\n  input_per_mtok: 0.8\n  output_per_mtok: 4\n"
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ENV_MODEL_PRICES, raising=False)
    monkeypatch.delenv("AVALIA_PG_DSN", raising=False)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ---------------- loader ----------------


def test_loads_yaml_json_and_toml(tmp_path: Path):
    expected = {
        "modelo-a": ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0),
        "modelo-b": ModelPrice(input_per_mtok=0.8, output_per_mtok=4.0),
    }
    assert load_model_prices(_write(tmp_path, "p.yaml", _YAML)) == expected
    json_text = (
        '{"modelo-a": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},'
        ' "modelo-b": {"input_per_mtok": 0.8, "output_per_mtok": 4}}'
    )
    assert load_model_prices(_write(tmp_path, "p.json", json_text)) == expected
    toml_text = (
        '["modelo-a"]\ninput_per_mtok = 3.0\noutput_per_mtok = 15.0\n'
        '["modelo-b"]\ninput_per_mtok = 0.8\noutput_per_mtok = 4\n'
    )
    assert load_model_prices(_write(tmp_path, "p.toml", toml_text)) == expected


def test_accepts_model_prices_wrapper_key(tmp_path: Path):
    text = "model_prices:\n" + "".join(f"  {line}\n" for line in _YAML.splitlines())
    assert set(load_model_prices(_write(tmp_path, "p.yml", text))) == {"modelo-a", "modelo-b"}


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [
        ("p.yaml", "modelo-a:\n  input_per_mtok: -1\n  output_per_mtok: 1\n", "preço inválido"),
        ("p.yaml", "modelo-a:\n  input_per_mtok: 1\n", "output_per_mtok"),
        ("p.yaml", "modelo-a: [1, 2\n", "malformado"),
        ("p.yaml", "", "vazio"),
        ("p.yaml", "- modelo-a\n", "vazio ou fora do formato"),
        ("p.ini", "[x]\n", "não suportado"),
    ],
)
def test_invalid_files_raise_descriptive_error(tmp_path: Path, name, text, message):
    with pytest.raises(ModelPricesError, match=message):
        load_model_prices(_write(tmp_path, name, text))


def test_missing_file_is_descriptive(tmp_path: Path):
    with pytest.raises(ModelPricesError, match="não foi possível ler"):
        load_model_prices(tmp_path / "nao-existe.yaml")


# ---------------- CLI ----------------


def test_cli_prices_flag_and_env_reach_the_config(tmp_path: Path, monkeypatch):
    prices = _write(tmp_path, "p.yaml", _YAML)
    args = _build_parser().parse_args(["alvo", "--prices", str(prices)])
    assert set(_make_config(args).model_prices) == {"modelo-a", "modelo-b"}

    monkeypatch.setenv(ENV_MODEL_PRICES, str(prices))
    args = _build_parser().parse_args(["alvo"])
    assert set(_make_config(args).model_prices) == {"modelo-a", "modelo-b"}  # fallback por env

    other = _write(tmp_path, "q.yaml", "modelo-c:\n  input_per_mtok: 1\n  output_per_mtok: 1\n")
    args = _build_parser().parse_args(["alvo", "--prices", str(other)])
    assert set(_make_config(args).model_prices) == {"modelo-c"}  # --prices vence o env


def test_cli_invalid_prices_file_is_input_error(tmp_path: Path, capsys):
    bad = _write(tmp_path, "p.yaml", "modelo-a:\n  input_per_mtok: -1\n  output_per_mtok: 1\n")
    rc = main([str(_FIXTURE), "--out", str(tmp_path / "o"), "--prices", str(bad)])
    err = capsys.readouterr().err
    assert rc == 2 and "preço inválido para 'modelo-a'" in err and "Traceback" not in err


def test_cli_warns_when_cost_ceiling_has_no_prices(tmp_path: Path, capsys):
    rc = main([str(_FIXTURE), "--out", str(tmp_path / "o"), "--cost-ceiling", "0.5"])
    assert rc == 0
    assert "--cost-ceiling sem tabela de preços" in capsys.readouterr().err


def test_cli_with_prices_records_them_in_the_report(tmp_path: Path):
    prices = _write(tmp_path, "p.yaml", _YAML)
    out = tmp_path / "o"
    assert (
        main([str(_FIXTURE), "--out", str(out), "--prices", str(prices), "--format", "json"]) == 0
    )
    assert '"modelo-a"' in (out / "laudo.json").read_text(encoding="utf-8")  # config efetiva


def test_warns_about_judge_models_without_price():
    gateway = ModelGateway(client_factory=lambda ref: None, env={})
    only_primary = EvaluatorConfig(
        model_prices={DEFAULT_PRIMARY_MODEL: ModelPrice(input_per_mtok=1, output_per_mtok=1)}
    )
    warnings = _price_warnings(only_primary, gateway)
    assert len(warnings) == 1 and DEFAULT_FALLBACK_MODEL in warnings[0]

    both = EvaluatorConfig(
        model_prices={
            m: ModelPrice(input_per_mtok=1, output_per_mtok=1)
            for m in (DEFAULT_PRIMARY_MODEL, DEFAULT_FALLBACK_MODEL)
        }
    )
    assert _price_warnings(both, gateway) == []
    assert _price_warnings(EvaluatorConfig(), None) == []  # modo determinístico, sem teto
