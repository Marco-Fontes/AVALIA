"""Loader validado da tabela de preços por modelo (DQ-01; RF-12, CA-13, RNF-06).

O teto de custo em MOEDA (`cost_ceiling`) só é calculável com o preço de cada modelo usado pelos
juízes. Preços são DADO do operador — mudam com o tempo e variam por contrato/provedor — e nunca
ficam embutidos no código (regra 2: nenhum slug de modelo como constante). Este módulo lê um
arquivo YAML, JSON ou TOML do próprio operador do AVALIA (não do alvo):

```yaml
# preço por milhão de tokens, na moeda que você usa para o teto
<slug-do-modelo>:
  input_per_mtok: 3.0
  output_per_mtok: 15.0
```

Aceita também o mapa dentro de uma chave `model_prices:`. Erros saem como `ModelPricesError`,
com o arquivo e a entrada problemática — o CLI os converte em erro de entrada (código 2).

Não executa o ALVO — só lê configuração do próprio AVALIA (RNF-05).
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml
from pydantic import ValidationError

from avalia.config.evaluator_config import ModelPrice

ENV_MODEL_PRICES = "AVALIA_MODEL_PRICES"  # caminho do arquivo de preços (alternativa a --prices)


class ModelPricesError(ValueError):
    """Arquivo de preços ausente, ilegível ou com entrada inválida."""


def _parse(path: Path, text: str) -> object:
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".toml":
        return tomllib.loads(text)
    raise ModelPricesError(
        f"formato de arquivo de preços não suportado: '{path.name}' (use .yaml, .yml, .json "
        "ou .toml)."
    )


def load_model_prices(path: str | Path) -> dict[str, ModelPrice]:
    """Lê e valida a tabela `slug → ModelPrice`. Erro descritivo em qualquer entrada inválida."""
    src = Path(path)
    try:
        text = src.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelPricesError(f"não foi possível ler o arquivo de preços '{src}': {exc}") from exc
    try:
        raw = _parse(src, text)
    except ModelPricesError:
        raise
    except Exception as exc:  # YAML/JSON/TOML malformado
        raise ModelPricesError(f"arquivo de preços malformado '{src}': {exc}") from exc

    if isinstance(raw, dict) and set(raw) == {"model_prices"}:
        raw = raw["model_prices"]
    if not isinstance(raw, dict) or not raw:
        raise ModelPricesError(
            f"arquivo de preços '{src}' vazio ou fora do formato "
            "`<slug>: {input_per_mtok: N, output_per_mtok: N}`."
        )

    prices: dict[str, ModelPrice] = {}
    for slug, entry in raw.items():
        if not isinstance(slug, str) or not slug.strip():
            raise ModelPricesError(f"slug de modelo inválido em '{src}': {slug!r}.")
        try:
            prices[slug.strip()] = ModelPrice.model_validate(entry)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'entrada'}: {err['msg']}"
                for err in exc.errors()
            )
            raise ModelPricesError(f"preço inválido para '{slug}' em '{src}': {problems}") from exc
    return prices
