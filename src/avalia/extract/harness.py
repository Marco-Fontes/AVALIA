"""T-107 — Detector ÚNICO de harness de teste/avaliação (RF-DIM-Q1, CA-06, CB-01).

Antes havia três heurísticas divergentes (inventário da ingestão, `has_harness` do TSM e
priorização), baseadas em SUBSTRING do caminho: `latest_version.py` "era" harness (casa `test_`)
e `tests/helpers.py` não era (`/tests/` exigia barra antes). Aqui a decisão é por PARTES do
caminho, e os três consumidores usam as mesmas funções (plan v1.4 §3.2g):

- `is_harness_path` — só o caminho: diretórios `tests`/`test`/`__tests__` em qualquer nível;
  `test_*.py`, `*_test.py`, `conftest.py`; `*.test.*`/`*.spec.*` em JS/TS.
- `file_signals_harness` — arquivos de config/CI que declaram execução de testes.
- `detect_harness` — existe harness no pacote? (caminho OU config).

Leitura de TEXTO apenas: nada importa nem executa o alvo (RNF-05/S-04).

Rastreabilidade: RF-DIM-Q1, CA-06, CB-01; plan §3.2g; tasks T-107.
"""

from __future__ import annotations

_TEST_DIRS = frozenset({"tests", "test", "__tests__"})
_HARNESS_FILES = frozenset({"conftest.py", "tox.ini", "pytest.ini", "noxfile.py"})
# Sufixos de código em que `nome.test.ext` / `nome.spec.ext` é convenção de teste (Jest/Vitest…).
_JS_TS_EXTS = frozenset({"js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts"})
_JS_TEST_CONFIGS = ("jest.config.", "vitest.config.", "playwright.config.")
_CI_TEST_COMMANDS = ("pytest", "unittest", "npm test", "npm run test", "jest", "vitest")


def _parts(path: str) -> list[str]:
    return [p for p in path.replace("\\", "/").lower().split("/") if p]


def is_harness_path(path: str) -> bool:
    """O CAMINHO indica um arquivo de teste? (comparação por partes, nunca por substring)"""
    parts = _parts(path)
    if not parts:
        return False
    *dirs, base = parts
    if any(d in _TEST_DIRS for d in dirs):
        return True
    if base == "conftest.py":
        return True
    if base.endswith(".py") and (base.startswith("test_") or base.endswith("_test.py")):
        return True
    tokens = base.split(".")
    return len(tokens) >= 3 and tokens[-2] in ("test", "spec") and tokens[-1] in _JS_TS_EXTS


def file_signals_harness(path: str, source: str) -> bool:
    """Arquivo de config/CI que declara execução de testes (T4.5)."""
    parts = _parts(path)
    if not parts:
        return False
    base = parts[-1]
    if base in _HARNESS_FILES or base.startswith(_JS_TEST_CONFIGS):
        return True
    if base == "pyproject.toml" and ("[tool.pytest" in source or "[tool.tox" in source):
        return True
    if base == "setup.cfg" and ("[tool:pytest]" in source or "[pytest]" in source):
        return True
    joined = "/".join(parts)
    if ".github/workflows/" in joined and base.endswith((".yml", ".yaml")):
        low = source.lower()
        return any(cmd in low for cmd in _CI_TEST_COMMANDS)
    return False


def detect_harness(files: dict[str, str]) -> bool:
    """RF-DIM-Q1: há harness de teste/avaliação no pacote (por caminho OU por config)?"""
    return any(
        is_harness_path(path) or file_signals_harness(path, source)
        for path, source in files.items()
    )
