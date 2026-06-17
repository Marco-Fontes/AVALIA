"""T1.1 — Extrator de config/dados (YAML/JSON/TOML/INI/`.env`) por leitura estática.

Faz com que arquivos de **configuração/dados** deixem de ser "não analisados" (best-effort)
e passem a alimentar o TSM com `ConfigItem`s (chaves achatadas), entrando em
`coverage.fully_analyzed`. Elimina o laudo PARCIAL espúrio disparado por um único `*.yaml`
sem parser (PLANO-MELHORIAS §3 / Frente 1).

Invariante RNF-05/S-04 (intrínseco): apenas **parsing de dados** (`yaml.safe_load`,
`json.loads`, `tomllib.loads`, `configparser`, parser de `.env` linha-a-linha). Nada importa,
executa ou avalia o alvo — o texto é dado inerte. Arquivo malformado → `unreadable_files`
(cai na legibilidade T-104), **nunca** levanta exceção.

`EvidenceRef`: `symbol` = caminho da chave (ex.: `rag.alucinacao`); `component_kind="config"`;
linha best-effort (`None` — a identidade usa símbolo, não linha — RF-29). Achatamento raso com
tetos de profundidade/quantidade para não explodir em lock files / JSON gigante (§10 Riscos).

Rastreabilidade: RF-01, RF-12, RF-14, RNF-07; resolução #1 (mesma interface `LanguageExtractor`).
"""

from __future__ import annotations

import configparser
import json
import tomllib

import yaml

from avalia.domain.evidence import EvidenceRef
from avalia.domain.tsm import ConfigItem
from avalia.extract.base import ExtractionResult

LANGUAGE = "config"

# Extensões de config/dados que este extrator entende (mapeadas no registry).
CONFIG_EXTENSIONS: tuple[str, ...] = (
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
)

# Tetos para manter o achatamento raso (evita ruído de lock files / JSON gigante — §10).
_MAX_DEPTH = 6
_MAX_ITEMS = 300
_MAX_VALUE_LEN = 200


def _scalar_expr(value: object) -> str:
    if value is None:
        return "null"
    text = str(value)
    return text[:_MAX_VALUE_LEN]


def _flatten(prefix: str, value: object, out: list[tuple[str, str]], depth: int) -> None:
    """Achata estruturas aninhadas em pares (caminho-da-chave, valor-expr), raso e limitado."""
    if len(out) >= _MAX_ITEMS or depth > _MAX_DEPTH:
        return
    if isinstance(value, dict):
        if not value:
            out.append((prefix or "<root>", "{}"))
            return
        for key, sub in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten(child, sub, out, depth + 1)
            if len(out) >= _MAX_ITEMS:
                return
    elif isinstance(value, list):
        if not value:
            out.append((prefix or "<root>", "[]"))
            return
        # Lista de escalares → registra a chave-pai com um resumo (mantém raso).
        if all(not isinstance(x, dict | list) for x in value):
            out.append((prefix or "<root>", _scalar_expr(value)))
            return
        for idx, sub in enumerate(value):
            _flatten(f"{prefix}[{idx}]", sub, out, depth + 1)
            if len(out) >= _MAX_ITEMS:
                return
    else:
        out.append((prefix or "<root>", _scalar_expr(value)))


def _parse(path: str, source: str) -> object:
    """Despacha por extensão → estrutura de dados. Levanta em malformado (capturado a montante)."""
    lower = path.lower()
    if lower.endswith((".yaml", ".yml")):
        yaml_data: object = yaml.safe_load(source)
        return yaml_data
    if lower.endswith(".json"):
        json_data: object = json.loads(source)
        return json_data
    if lower.endswith(".toml"):
        toml_data: object = tomllib.loads(source)
        return toml_data
    if lower.endswith(".env"):
        return _parse_env(source)
    # .ini / .cfg
    parser = configparser.ConfigParser()
    parser.optionxform = str  # type: ignore[assignment]  # preserva a caixa das chaves
    parser.read_string(source)
    result: dict[str, object] = {}
    for section in parser.sections():
        result[section] = dict(parser.items(section))
    if parser.defaults():
        result["DEFAULT"] = dict(parser.defaults())
    return result


def _parse_env(source: str) -> dict[str, object]:
    """Parser simples de `.env`: `CHAVE=valor` linha a linha (ignora comentários/branco)."""
    out: dict[str, object] = {}
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip("'\"")
        out[key] = value
    return out


def _config_items(path: str, parsed: object) -> list[ConfigItem]:
    flat: list[tuple[str, str]] = []
    _flatten("", parsed, flat, depth=0)
    items: list[ConfigItem] = []
    for key, value_expr in flat:
        symbol = key or "<root>"
        items.append(
            ConfigItem(
                key=symbol,
                value_expr=value_expr,
                evidence=EvidenceRef(
                    file_path=path,
                    symbol=symbol,
                    component_kind="config",
                    snippet=value_expr or None,
                ),
            )
        )
    return items


class ConfigExtractor:
    """Extrator estático de config/dados. Implementa `LanguageExtractor` (mesma porta de T-101)."""

    language = LANGUAGE

    def extract(self, files: dict[str, str]) -> ExtractionResult:
        seen: list[str] = []
        configs: list[ConfigItem] = []
        unreadable: list[str] = []
        for path, source in files.items():
            seen.append(path)
            try:
                parsed = _parse(path, source)
            except Exception:  # parse malformado → unreadable (T-104), nunca quebra a ingestão
                unreadable.append(path)
                continue
            configs.extend(_config_items(path, parsed))
        return ExtractionResult(files=seen, configs=configs, unreadable_files=unreadable)
